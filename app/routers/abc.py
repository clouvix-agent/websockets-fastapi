import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import re
from typing import List, Dict
from langchain_core.runnables import RunnableConfig

from langchain_core.tools import tool
@tool
def get_recommendations_for_all_metrics(config: RunnableConfig) -> str:
    """
    Fetches metrics for a given user_id, compares them with cost table rules,
    and returns recommendations for all resource types (EC2, S3, RDS, Lambda) as a formatted string.
    
    Args:
        config (RunnableConfig): Contains user_id in config['configurable']
    
    Returns:
        str: Formatted string containing recommendations or a message if none are found.
    """
    user_id = config.get('configurable', {}).get('user_id', 'unknown')
    try:
        # Load DATABASE_URL from .env file
        load_dotenv()
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            raise ValueError("DATABASE_URL not found in .env file")

        # Set up SQLAlchemy engine
        engine = create_engine(database_url)

        recommendations = []

        with engine.connect() as connection:
            # Fetch all metrics for the given user_id
            metrics_query = text("""
                SELECT resource_type, resource_identifier, metrics_data
                FROM metrics
                WHERE userid = :user_id;
            """)
            metrics_result = connection.execute(metrics_query, {"user_id": user_id}).mappings().fetchall()

            # Fetch all rules from cost table
            cost_query = text("""
                SELECT resource_type, rule, recommendation
                FROM cost
            """)
            cost_result = connection.execute(cost_query).mappings().fetchall()

            # Organize cost rules by resource_type for easy lookup
            cost_rules_by_type = {}
            for row in cost_result:
                resource_type = row['resource_type']
                if resource_type not in cost_rules_by_type:
                    cost_rules_by_type[resource_type] = []
                cost_rules_by_type[resource_type].append({
                    'rule': row['rule'],
                    'recommendation': row['recommendation']
                })

            # Process each metric record
            for metric in metrics_result:
                resource_type = metric['resource_type']
                resource_id = metric['resource_identifier']
                metrics_data = metric['metrics_data']

                # Skip if no rules exist for this resource_type
                if resource_type not in cost_rules_by_type:
                    continue

                # Extract relevant metrics based on resource_type
                for rule_info in cost_rules_by_type[resource_type]:
                    rule = rule_info['rule']
                    recommendation = rule_info['recommendation']

                    # EC2 and RDS rules (AvgCPU, MaxCPU)
                    if resource_type in ['EC2', 'RDS']:
                        # Handle AvgCPU rules
                        avg_cpu_match = re.match(r'AvgCPU\s*(>|<)\s*(\d+\.?\d*)', rule)
                        if avg_cpu_match:
                            operator, threshold = avg_cpu_match.groups()
                            threshold = float(threshold)
                            avg_cpu_str = metrics_data.get('AvgCPU') or \
                                        metrics_data.get('Metrics', {}).get('CPUUtilization', {}).get('Average', '0%')
                            try:
                                avg_cpu = float(avg_cpu_str.replace('%', ''))
                                if (operator == '>' and avg_cpu > threshold) or \
                                   (operator == '<' and avg_cpu < threshold):
                                    recommendations.append({
                                        'resource_type': resource_type,
                                        'resource_identifier': resource_id,
                                        'metric': f"AvgCPU: {avg_cpu}%",
                                        'rule': rule,
                                        'recommendation': recommendation
                                    })
                            except ValueError:
                                print(f"Invalid AvgCPU format for {resource_id}: {avg_cpu_str}")

                        # Handle MaxCPU rules
                        max_cpu_match = re.match(r'MaxCPU\s*>\s*(\d+\.?\d*)', rule)
                        if max_cpu_match:
                            threshold = float(max_cpu_match.group(1))
                            max_cpu_str = metrics_data.get('MaxCPU') or \
                                        metrics_data.get('Metrics', {}).get('CPUUtilization', {}).get('Maximum', '0%')
                            try:
                                max_cpu = float(max_cpu_str.replace('%', ''))
                                if max_cpu > threshold:
                                    recommendations.append({
                                        'resource_type': resource_type,
                                        'resource_identifier': resource_id,
                                        'metric': f"MaxCPU: {max_cpu}%",
                                        'rule': rule,
                                        'recommendation': recommendation
                                    })
                            except ValueError:
                                print(f"Invalid MaxCPU format for {resource_id}: {max_cpu_str}")

                    # S3 rules (BucketSizeMB, NumberOfObjects)
                    elif resource_type == 'S3':
                        metrics = metrics_data.get('Metrics', {})
                        bucket_size_mb = float(metrics.get('BucketSizeMB', 0))
                        num_objects = int(metrics.get('NumberOfObjects', 0))

                        # Handle BucketSizeMB rules
                        size_match = re.match(r'BucketSizeMB\s*>\s*(\d+\.?\d*)', rule)
                        if size_match:
                            threshold = float(size_match.group(1))
                            if bucket_size_mb > threshold:
                                recommendations.append({
                                    'resource_type': resource_type,
                                    'resource_identifier': resource_id,
                                    'metric': f"BucketSizeMB: {bucket_size_mb}",
                                    'rule': rule,
                                    'recommendation': recommendation
                                })

                        # Handle NumberOfObjects rules
                        objects_match = re.match(r'NumberOfObjects\s*>\s*(\d+)', rule)
                        if objects_match:
                            threshold = int(objects_match.group(1))
                            if num_objects > threshold:
                                recommendations.append({
                                    'resource_type': resource_type,
                                    'resource_identifier': resource_id,
                                    'metric': f"NumberOfObjects: {num_objects}",
                                    'rule': rule,
                                    'recommendation': recommendation
                                })

                        # Handle BucketSizeMB > 100 and low access (simplified, assuming low access not available)
                        if 'BucketSizeMB > 100 and low access' in rule and bucket_size_mb > 100:
                            recommendations.append({
                                'resource_type': resource_type,
                                'resource_identifier': resource_id,
                                'metric': f"BucketSizeMB: {bucket_size_mb} (assuming low access)",
                                'rule': rule,
                                'recommendation': recommendation
                            })

                    # Lambda rules (Errors.Total, Duration.Average, Throttles.Total, Invocations.Total)
                    elif resource_type == 'Lambda':
                        metrics = metrics_data.get('Metrics', {})
                        errors_total = int(metrics.get('Errors', {}).get('Total', 0))
                        # Handle Duration.Average with potential 'ms' suffix
                        duration_avg_str = str(metrics.get('Duration', {}).get('Average', '0'))
                        try:
                            # Remove non-numeric characters except decimal point
                            duration_avg = float(re.sub(r'[^\d.]', '', duration_avg_str))
                        except ValueError:
                            print(f"Invalid Duration.Average format for {resource_id}: {duration_avg_str}")
                            duration_avg = 0.0
                        throttles_total = int(metrics.get('Throttles', {}).get('Total', 0))
                        invocations_total = int(metrics.get('Invocations', {}).get('Total', 0))

                        # Handle Errors.Total
                        errors_match = re.match(r'Errors\.Total\s*>\s*(\d+)', rule)
                        if errors_match:
                            threshold = int(errors_match.group(1))
                            if errors_total > threshold:
                                recommendations.append({
                                    'resource_type': resource_type,
                                    'resource_identifier': resource_id,
                                    'metric': f"Errors.Total: {errors_total}",
                                    'rule': rule,
                                    'recommendation': recommendation
                                })

                        # Handle Duration.Average
                        duration_match = re.match(r'Duration\.Average\s*>\s*(\d+\.?\d*)ms', rule)
                        if duration_match:
                            threshold = float(duration_match.group(1))
                            if duration_avg > threshold:
                                recommendations.append({
                                    'resource_type': resource_type,
                                    'resource_identifier': resource_id,
                                    'metric': f"Duration.Average: {duration_avg}ms",
                                    'rule': rule,
                                    'recommendation': recommendation
                                })

                        # Handle Throttles.Total
                        throttles_match = re.match(r'Throttles\.Total\s*>\s*(\d+)', rule)
                        if throttles_match:
                            threshold = int(throttles_match.group(1))
                            if throttles_total > threshold:
                                recommendations.append({
                                    'resource_type': resource_type,
                                    'resource_identifier': resource_id,
                                    'metric': f"Throttles.Total: {throttles_total}",
                                    'rule': rule,
                                    'recommendation': recommendation
                                })

                        # Handle Invocations.Total
                        invocations_match = re.match(r'Invocations\.Total\s*=\s*(\d+)', rule)
                        if invocations_match:
                            threshold = int(invocations_match.group(1))
                            if invocations_total == threshold:
                                recommendations.append({
                                    'resource_type': resource_type,
                                    'resource_identifier': resource_id,
                                    'metric': f"Invocations.Total: {invocations_total}",
                                    'rule': rule,
                                    'recommendation': recommendation
                                })

        # Format recommendations as a string
        if recommendations:
            output = []
            for rec in recommendations:
                output.append(
                    f"Resource Type: {rec['resource_type']}\n"
                    f"Resource: {rec['resource_identifier']}\n"
                    f"Metric: {rec['metric']}\n"
                    f"Rule: {rec['rule']}\n"
                    f"Recommendation: {rec['recommendation']}\n"
                    f"{'-' * 50}"
                )
            return "\n".join(output)
        else:
            return f"No recommendations found for user_id={user_id}"

    except Exception as e:
        return f"Error: {str(e)}"