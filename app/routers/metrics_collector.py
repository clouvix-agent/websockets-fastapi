import boto3
import json
import datetime
import logging
import os
import time
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import re
from typing import List, Dict, Any
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from openai import OpenAI

import concurrent.futures
import threading
# Load environment variables (only for DATABASE_URL)
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in environment variables")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class AWSMetricsCollector:
    def __init__(self, aws_access_key_id, aws_secret_access_key, region_name):
        """Initialize the AWS Metrics Collector with credentials"""
        self.session = boto3.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name
        )
        self.ec2_client = self.session.client('ec2')
        self.s3_client = self.session.client('s3')
        self.rds_client = self.session.client('rds')
        self.lambda_client = self.session.client('lambda')
        self.cloudwatch = self.session.client('cloudwatch')
        self.sts_client = self.session.client('sts')
        self.account_id = self.sts_client.get_caller_identity()['Account']
        self.region_name = region_name
        self.metrics_data = {
            'EC2': [],
            'S3': [],
            'RDS': [],
            'Lambda': []
        }

    def collect_ec2_metrics(self):
        """Collect EC2 instance metrics with recommendations and ARN"""
        try:
            paginator = self.ec2_client.get_paginator('describe_instances')
            instances = []
            
            for page in paginator.paginate():
                for reservation in page['Reservations']:
                    for instance in reservation['Instances']:
                        if instance['State']['Name'] == 'running':
                            instances.append(instance)
            
            logger.info(f"Found {len(instances)} running EC2 instances")
            
            for instance in instances:
                instance_id = instance['InstanceId']
                instance_type = instance['InstanceType']
                # Construct EC2 ARN
                instance_arn = f"arn:aws:ec2:{self.region_name}:{self.account_id}:instance/{instance_id}"
                
                instance_name = None
                if 'Tags' in instance:
                    for tag in instance['Tags']:
                        if tag['Key'] == 'Name':
                            instance_name = tag['Value']
                            break
                
                if not instance_name:
                    instance_name = instance_id
                
                cpu_response = self.cloudwatch.get_metric_statistics(
                    Namespace='AWS/EC2',
                    MetricName='CPUUtilization',
                    Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                    StartTime=datetime.datetime.now() - datetime.timedelta(days=14),
                    EndTime=datetime.datetime.now(),
                    Period=86400,
                    Statistics=['Average', 'Maximum']
                )
                
                recommendation = None
                if cpu_response['Datapoints']:
                    avg_cpu = sum(point['Average'] for point in cpu_response['Datapoints']) / len(cpu_response['Datapoints'])
                    max_cpu = max(point['Maximum'] for point in cpu_response['Datapoints']) if cpu_response['Datapoints'] else 0
                    
                    if avg_cpu < 20:
                        recommendation = "Downsize the instance."
                    elif avg_cpu > 80:
                        recommendation = "Upgrade the instance."
                    
                    daily_metrics = []
                    for point in sorted(cpu_response['Datapoints'], key=lambda x: x['Timestamp']):
                        daily_metrics.append({
                            'Date': point['Timestamp'].strftime('%Y-%m-%d'),
                            'AvgCPU': f"{point['Average']:.2f}%",
                            'MaxCPU': f"{point['Maximum']:.2f}%"
                        })
                    
                    self.metrics_data['EC2'].append({
                        'ARN': instance_arn,
                        'InstanceId': instance_id,
                        'InstanceName': instance_name,
                        'InstanceType': instance_type,
                        'AvgCPU': f"{avg_cpu:.2f}%",
                        'MaxCPU': f"{max_cpu:.2f}%",
                        'Recommendation': recommendation,
                        'DailyMetrics': daily_metrics
                    })
                    
                    if recommendation:
                        print(f"  Recommendation: {recommendation}")
                    print("-" * 50)
                else:
                    logger.warning(f"No CloudWatch data available for instance {instance_id}")
                    self.metrics_data['EC2'].append({
                        'ARN': instance_arn,
                        'InstanceId': instance_id,
                        'InstanceName': instance_name,
                        'InstanceType': instance_type,
                        'AvgCPU': None,
                        'MaxCPU': None,
                        'DailyMetrics': [],
                        'Recommendation': None
                    })
        
        except Exception as e:
            logger.error(f"Error collecting EC2 metrics: {e}")

    def collect_s3_metrics(self):
        """Collect S3 bucket metrics with ARN"""
        try:
            buckets = self.s3_client.list_buckets()
            logger.info(f"Found {len(buckets['Buckets'])} S3 buckets")

            for bucket in buckets['Buckets']:
                bucket_name = bucket['Name']
                bucket_region = self.get_bucket_region(bucket_name)
                # Construct S3 ARN
                bucket_arn = f"arn:aws:s3:::{bucket_name}"

                if bucket_region != self.session.region_name:
                    logger.info(f"Skipping bucket {bucket_name} as it's in a different region: {bucket_region}")
                    continue

                bucket_metrics = {
                    'BucketSizeBytes': 0,
                    'NumberOfObjects': 0
                }

                try:
                    size_metrics = self.cloudwatch.get_metric_statistics(
                        Namespace='AWS/S3',
                        MetricName='BucketSizeBytes',
                        Dimensions=[
                            {'Name': 'BucketName', 'Value': bucket_name},
                            {'Name': 'StorageType', 'Value': 'StandardStorage'}
                        ],
                        StartTime=datetime.datetime.now() - datetime.timedelta(days=14),
                        EndTime=datetime.datetime.now(),
                        Period=86400,
                        Statistics=['Average']
                    )

                    if not size_metrics['Datapoints']:
                        logger.warning(f"No CloudWatch size data for bucket {bucket_name} in the last 14 days")
                    else:
                        latest_point = max(size_metrics['Datapoints'], key=lambda x: x['Timestamp'])
                        bucket_metrics['BucketSizeBytes'] = latest_point['Average']
                        bucket_size_mb = latest_point['Average'] / (1024 * 1024)
                        bucket_metrics['BucketSizeMB'] = round(bucket_size_mb, 2)

                    object_count_metrics = self.cloudwatch.get_metric_statistics(
                        Namespace='AWS/S3',
                        MetricName='NumberOfObjects',
                        Dimensions=[
                            {'Name': 'BucketName', 'Value': bucket_name},
                            {'Name': 'StorageType', 'Value': 'AllStorageTypes'}
                        ],
                        StartTime=datetime.datetime.now() - datetime.timedelta(days=14),
                        EndTime=datetime.datetime.now(),
                        Period=86400,
                        Statistics=['Average']
                    )

                    if not object_count_metrics['Datapoints']:
                        logger.warning(f"No CloudWatch object count data for bucket {bucket_name} in the last 14 days")
                    else:
                        latest_point = max(object_count_metrics['Datapoints'], key=lambda x: x['Timestamp'])
                        bucket_metrics['NumberOfObjects'] = int(latest_point['Average'])

                except ClientError as e:
                    logger.warning(f"Error getting CloudWatch metrics for bucket {bucket_name}: {e}")
                    try:
                        logger.info(f"Falling back to list_object_versions for {bucket_name}")
                        total_size = 0
                        total_objects = 0
                        paginator = self.s3_client.get_paginator('list_object_versions')
                        for page in paginator.paginate(Bucket=bucket_name):
                            if 'Versions' in page:
                                for version in page['Versions']:
                                    total_size += version['Size']
                                    total_objects += 1
                        bucket_metrics['BucketSizeBytes'] = total_size
                        bucket_metrics['BucketSizeMB'] = round(total_size / (1024 * 1024), 2)
                        bucket_metrics['NumberOfObjects'] = total_objects
                    except ClientError as list_error:
                        logger.warning(f"Error listing objects for bucket {bucket_name}: {list_error}")

                self.metrics_data['S3'].append({
                    'ARN': bucket_arn,
                    'BucketName': bucket_name,
                    'BucketRegion': bucket_region,
                    'Metrics': bucket_metrics
                })

        except Exception as e:
            logger.error(f"Error collecting S3 metrics: {e}")

    def collect_rds_metrics(self):
        """Collect RDS instance metrics with recommendations and ARN"""
        try:
            response = self.rds_client.describe_db_instances()
            instances = response['DBInstances']
            
            logger.info(f"Found {len(instances)} RDS instances")

            for instance in instances:
                db_instance_identifier = instance['DBInstanceIdentifier']
                db_instance_class = instance['DBInstanceClass']
                engine = instance['Engine']
                db_instance_status = instance['DBInstanceStatus']
                # Get RDS ARN directly from the response
                db_instance_arn = instance['DBInstanceArn']

                if db_instance_status != 'available':
                    logger.info(f"Skipping RDS instance {db_instance_identifier} (status: {db_instance_status})")
                    continue

                cpu_response = self.cloudwatch.get_metric_statistics(
                    Namespace='AWS/RDS',
                    MetricName='CPUUtilization',
                    Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_instance_identifier}],
                    StartTime=datetime.datetime.now() - datetime.timedelta(days=14),
                    EndTime=datetime.datetime.now(),
                    Period=86400,
                    Statistics=['Average', 'Maximum']
                )

                rds_metrics = {
                    'CPUUtilization': {
                        'Average': 0,
                        'Maximum': 0,
                        'DailyMetrics': []
                    }
                }

                recommendation = None
                if cpu_response['Datapoints']:
                    avg_cpu = sum(point['Average'] for point in cpu_response['Datapoints']) / len(cpu_response['Datapoints'])
                    max_cpu = max(point['Maximum'] for point in cpu_response['Datapoints']) if cpu_response['Datapoints'] else 0

                    if avg_cpu < 20:
                        recommendation = "Downsize the RDS instance."
                    elif avg_cpu > 80:
                        recommendation = "Upgrade the RDS instance."

                    daily_metrics = []
                    for point in sorted(cpu_response['Datapoints'], key=lambda x: x['Timestamp']):
                        daily_metrics.append({
                            'Date': point['Timestamp'].strftime('%Y-%m-%d'),
                            'AvgCPU': f"{point['Average']:.2f}%",
                            'MaxCPU': f"{point['Maximum']:.2f}%"
                        })

                    rds_metrics['CPUUtilization'] = {
                        'Average': f"{avg_cpu:.2f}%",
                        'Maximum': f"{max_cpu:.2f}%",
                        'DailyMetrics': daily_metrics
                    }

                    self.metrics_data['RDS'].append({
                        'ARN': db_instance_arn,
                        'InstanceId': db_instance_identifier,
                        'DBInstanceClass': db_instance_class,
                        'Engine': engine,
                        'Metrics': rds_metrics,
                        'Recommendation': recommendation
                    })

                    if recommendation:
                        print(f"  Recommendation: {recommendation}")
                    print("-" * 50)
                else:
                    logger.warning(f"No CloudWatch data available for RDS instance {db_instance_identifier}")
                    self.metrics_data['RDS'].append({
                        'ARN': db_instance_arn,
                        'DBInstanceIdentifier': db_instance_identifier,
                        'DBInstanceClass': db_instance_class,
                        'Engine': engine,
                        'Metrics': rds_metrics,
                        'Recommendation': None
                    })

        except Exception as e:
            logger.error(f"Error collecting RDS metrics: {e}")

    def collect_lambda_metrics(self):
        """Collect Lambda function metrics with recommendations and ARN"""
        try:
            paginator = self.lambda_client.get_paginator('list_functions')
            functions = []
            
            for page in paginator.paginate():
                functions.extend(page['Functions'])
            
            logger.info(f"Found {len(functions)} Lambda functions")

            for function in functions:
                function_name = function['FunctionName']
                runtime = function.get('Runtime', 'N/A')
                # Get Lambda ARN directly from the response
                function_arn = function['FunctionArn']
                
                lambda_metrics = {
                    'Invocations': {
                        'Total': 0,
                        'DailyMetrics': []
                    },
                    'Duration': {
                        'Average': 0,
                        'Maximum': 0,
                        'DailyMetrics': []
                    },
                    'Errors': {
                        'Total': 0,
                        'DailyMetrics': []
                    },
                    'Throttles': {
                        'Total': 0,
                        'DailyMetrics': []
                    }
                }

                start_time = datetime.datetime.now() - datetime.timedelta(days=14)
                end_time = datetime.datetime.now()

                invocations_response = self.cloudwatch.get_metric_statistics(
                    Namespace='AWS/Lambda',
                    MetricName='Invocations',
                    Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=86400,
                    Statistics=['Sum']
                )

                if invocations_response['Datapoints']:
                    total_invocations = sum(point['Sum'] for point in invocations_response['Datapoints'])
                    daily_metrics = []
                    for point in sorted(invocations_response['Datapoints'], key=lambda x: x['Timestamp']):
                        daily_metrics.append({
                            'Date': point['Timestamp'].strftime('%Y-%m-%d'),
                            'Invocations': int(point['Sum'])
                        })
                    lambda_metrics['Invocations'] = {
                        'Total': int(total_invocations),
                        'DailyMetrics': daily_metrics
                    }

                duration_response = self.cloudwatch.get_metric_statistics(
                    Namespace='AWS/Lambda',
                    MetricName='Duration',
                    Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=86400,
                    Statistics=['Average', 'Maximum']
                )

                recommendation = None
                if duration_response['Datapoints']:
                    avg_duration = sum(point['Average'] for point in duration_response['Datapoints']) / len(duration_response['Datapoints'])
                    max_duration = max(point['Maximum'] for point in duration_response['Datapoints']) if duration_response['Datapoints'] else 0

                    if avg_duration >= 810000:
                        recommendation = "Function execution time is too high, consider optimizing the function."

                    daily_metrics = []
                    for point in sorted(duration_response['Datapoints'], key=lambda x: x['Timestamp']):
                        daily_metrics.append({
                            'Date': point['Timestamp'].strftime('%Y-%m-%d'),
                            'AvgDuration': f"{point['Average']:.2f} ms",
                            'MaxDuration': f"{point['Maximum']:.2f} ms"
                        })
                    lambda_metrics['Duration'] = {
                        'Average': f"{avg_duration:.2f} ms",
                        'Maximum': f"{max_duration:.2f} ms",
                        'DailyMetrics': daily_metrics
                    }

                errors_response = self.cloudwatch.get_metric_statistics(
                    Namespace='AWS/Lambda',
                    MetricName='Errors',
                    Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=86400,
                    Statistics=['Sum']
                )

                if errors_response['Datapoints']:
                    total_errors = sum(point['Sum'] for point in errors_response['Datapoints'])
                    daily_metrics = []
                    for point in sorted(errors_response['Datapoints'], key=lambda x: x['Timestamp']):
                        daily_metrics.append({
                            'Date': point['Timestamp'].strftime('%Y-%m-%d'),
                            'Errors': int(point['Sum'])
                        })
                    lambda_metrics['Errors'] = {
                        'Total': int(total_errors),
                        'DailyMetrics': daily_metrics
                    }

                throttles_response = self.cloudwatch.get_metric_statistics(
                    Namespace='AWS/Lambda',
                    MetricName='Throttles',
                    Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=86400,
                    Statistics=['Sum']
                )

                if throttles_response['Datapoints']:
                    total_throttles = sum(point['Sum'] for point in throttles_response['Datapoints'])
                    daily_metrics = []
                    for point in sorted(throttles_response['Datapoints'], key=lambda x: x['Timestamp']):
                        daily_metrics.append({
                            'Date': point['Timestamp'].strftime('%Y-%m-%d'),
                            'Throttles': int(point['Sum'])
                        })
                    lambda_metrics['Throttles'] = {
                        'Total': int(total_throttles),
                        'DailyMetrics': daily_metrics
                    }

                self.metrics_data['Lambda'].append({
                    'ARN': function_arn,
                    'FunctionName': function_name,
                    'Runtime': runtime,
                    'Metrics': lambda_metrics,
                    'Recommendation': recommendation
                })

                if recommendation:
                    print(f"  Recommendation: {recommendation}")
                print("-" * 50)

        except Exception as e:
            logger.error(f"Error collecting Lambda metrics: {e}")

    def get_bucket_region(self, bucket_name):
        """Get the region of an S3 bucket"""
        try:
            location = self.s3_client.get_bucket_location(Bucket=bucket_name)
            region = location['LocationConstraint']
            if region is None:
                return 'us-east-1'
            return region
        except Exception as e:
            logger.warning(f"Error getting region for bucket {bucket_name}: {e}")
            return 'unknown'

    def run_collection(self):
        """Run the complete metrics collection"""
        try:
            self.collect_ec2_metrics()
            self.collect_s3_metrics()
            self.collect_rds_metrics()
            self.collect_lambda_metrics()
            
            return self.metrics_data
        
        except Exception as e:
            logger.error(f"Error running metrics collection: {e}")
            raise

def fetch_aws_credentials():
    """Fetch AWS credentials from the connections table where type='aws'."""
    try:
        with SessionLocal() as session:
            query = """
                SELECT userid, connection_json
                FROM connections
                WHERE type = 'aws'
            """
            result = session.execute(text(query)).fetchall()
            credentials_list = []

            for row in result:
                # Access Row object using column names
                userid = row.userid
                connection_json = row.connection_json
                
                # Parse the JSONB connection_json
                try:
                    connection_data = json.loads(connection_json)
                    access_key = None
                    secret_key = None
                    region = 'us-east-1'  # Default region if not specified

                    for item in connection_data:
                        if item['key'] == 'AWS_ACCESS_KEY_ID':
                            access_key = item['value']
                        elif item['key'] == 'AWS_SECRET_ACCESS_KEY':
                            secret_key = item['value']
                        elif item['key'] == 'AWS_REGION':
                            region = item['value']

                    if access_key and secret_key:
                        credentials_list.append({
                            'userid': userid,
                            'access_key': access_key,
                            'secret_key': secret_key,
                            'region': region
                        })
                    else:
                        logger.warning(f"Missing AWS credentials for userid {userid}")
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing connection_json for userid {userid}: {e}")
            
            return credentials_list

    except Exception as e:
        logger.error(f"Error fetching AWS credentials from connections table: {e}")
        return []

# def fetch_and_save_metrics():
#     output_file = 'aws_metrics.json'
#     while True:
#         try:
#             print("Starting AWS metrics collection cycle")
            
#             # Fetch AWS credentials from connections table
#             credentials_list = fetch_aws_credentials()
            
#             if not credentials_list:
#                 logger.error("No valid AWS credentials found in connections table")
#                 time.sleep(30)
#                 continue

#             for creds in credentials_list:
#                 userid = creds['userid']
#                 access_key = creds['access_key']
#                 secret_key = creds['secret_key']
#                 region = creds['region']

#                 print(f"Collecting metrics for userid {userid} in region {region}")
#                 try:
#                     # Initialize AWSMetricsCollector and collect metrics
#                     collector = AWSMetricsCollector(
#                         aws_access_key_id=access_key,
#                         aws_secret_access_key=secret_key,
#                         region_name=region
#                     )
                    
#                     logger.info(f"Running metrics collection for userid {userid}")
#                     metrics_data = collector.run_collection()
                    
#                     # Save metrics to JSON file (optional, can be removed if only DB storage is needed)
#                     print(f"Saving metrics to {output_file} for userid {userid}")
#                     with open(f"{userid}_{output_file}", 'w') as f:
#                         json.dump({
#                             'generatedAt': datetime.datetime.now().isoformat(),
#                             'metrics': metrics_data,
#                             'userid': userid
#                         }, f, indent=2)
                    
#                     # Insert metrics into database
#                     logger.info(f"Inserting metrics into database for userid {userid}")
#                     insert_metrics_to_db(metrics_data, userid)
                    
#                     print(f"Metrics collection completed for userid {userid}")
                
#                 except ClientError as e:
#                     if e.response['Error']['Code'] == 'InvalidClientTokenId':
#                         logger.error(f"Invalid AWS credentials for userid {userid}: {str(e)}")
#                         print(f"Skipping userid {userid} due to invalid credentials")
#                         continue
#                     else:
#                         logger.error(f"AWS error for userid {userid}: {str(e)}")
#                         raise  # Re-raise other AWS errors
#                 except Exception as e:
#                     logger.error(f"Error collecting metrics for userid {userid}: {str(e)}", exc_info=True)
#                     print(f"Skipping userid {userid} due to error: {str(e)}")
#                     continue
            
#             print("Metrics collection cycle completed for all AWS accounts. Sleeping for 120 seconds")
        
#         except Exception as e:
#             logger.error(f"Error in metrics collection cycle: {str(e)}", exc_info=True)
        
#         time.sleep(120)
def fetch_and_save_metrics():
    output_file = 'aws_metrics.json'
    
    while True:
        try:
            print("Starting AWS metrics collection cycle")
            
            # Fetch AWS credentials from connections table
            credentials_list = fetch_aws_credentials()
            
            if not credentials_list:
                logger.error("No valid AWS credentials found in connections table")
                time.sleep(30)
                continue
            
            for creds in credentials_list:
                userid = creds['userid']
                access_key = creds['access_key']
                secret_key = creds['secret_key']
                region = creds['region']
                
                try:
                    # Use ThreadPoolExecutor to run metrics collection and recommendation generation concurrently
                    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                        # First submit the metrics collection task
                        metrics_future = executor.submit(
                            collect_metrics_for_user, 
                            userid, 
                            access_key, 
                            secret_key, 
                            region, 
                            output_file
                        )
                        
                        # Get the metrics results (this will wait until metrics collection is done)
                        metrics_success = metrics_future.result()
                        
                        if metrics_success:
                            # If metrics collection was successful, generate and save recommendations
                            recommendations_future = executor.submit(
                                process_recommendations_for_user,
                                userid
                            )
                            
                            # Wait for recommendations to complete
                            recommendations_future.result()
                    
                except Exception as e:
                    logger.error(f"Error processing user {userid}: {str(e)}", exc_info=True)
                    continue
            
            print("Metrics and recommendations cycle completed for all AWS accounts. Sleeping for 120 seconds")
            
        except Exception as e:
            logger.error(f"Error in metrics collection cycle: {str(e)}", exc_info=True)
        
        time.sleep(86400)

def insert_metrics_to_db(metrics_data, userid):
    """Insert metrics into the metrics table with userid."""
    try:
        generated_at = datetime.datetime.now().isoformat()

        # Create a database session
        with SessionLocal() as session:
            try:
                # Insert metrics for each resource type
                for resource_type, resources in metrics_data.items():
                    for resource in resources:
                        arn = resource.get('ARN')
                        resource_identifier = (
                            resource.get('InstanceId') or
                            resource.get('BucketName') or
                            resource.get('DBInstanceIdentifier') or
                            resource.get('FunctionName')
                        )

                        # Prepare metrics_data for JSONB
                        resource_metrics = {k: v for k, v in resource.items() if k != 'ARN'}
                        # Remove fields not stored in metrics_data JSONB
                        for key in ['Recommendation', 'InstanceId', 'BucketName', 
                                  'DBInstanceIdentifier', 'FunctionName']:
                            if key in resource_metrics:
                                del resource_metrics[key]

                        # SQL query to insert or update metrics
                        query = """
                            INSERT INTO metrics (
                                generated_at, resource_type, arn, resource_identifier,
                                metrics_data, userid,
                                created_at, updated_at
                            ) VALUES (
                                :generated_at, :resource_type, :arn, :resource_identifier,
                                :metrics_data, :userid,
                                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                            )
                            ON CONFLICT ON CONSTRAINT unique_arn_resource_type
                            DO UPDATE SET
                                generated_at = EXCLUDED.generated_at,
                                metrics_data = EXCLUDED.metrics_data,
                                userid = EXCLUDED.userid,
                                updated_at = CURRENT_TIMESTAMP
                        """

                        session.execute(text(query), {
                            'generated_at': generated_at,
                            'resource_type': resource_type,
                            'arn': arn,
                            'resource_identifier': resource_identifier,
                            'metrics_data': json.dumps(resource_metrics),
                            'userid': userid
                        })

                session.commit()
                logger.info(f"Successfully inserted/updated metrics for userid {userid}")

            except Exception as e:
                session.rollback()
                logger.error(f"Error inserting metrics into database for userid {userid}: {str(e)}")
                raise

    except Exception as e:
        logger.error(f"Error in insert_metrics_to_db for userid {userid}: {str(e)}")


def get_llm_recommendation(openai_client: OpenAI, resource_type: str, resource_id: str, instance_type: str | None, db_instance_class: str | None, rule: str, recommendation: str) -> str:
    """
    Calls the OpenAI LLM to refine a recommendation for a given resource type, rule, and original recommendation.

    Args:
        openai_client (OpenAI): Initialized OpenAI client.
        resource_type (str): Type of resource (e.g., EC2, RDS, S3, Lambda).
        resource_id (str): Identifier of the resource (e.g., instance ID, bucket name).
        instance_type (str | None): EC2 instance type (if applicable), None for other resources.
        db_instance_class (str | None): RDS DB instance class (if applicable), None for other resources.
        rule (str): The rule that triggered the recommendation (e.g., 'AvgCPU > 80').
        recommendation (str): The original recommendation from the cost table.

    Returns:
        str: Refined recommendation from the LLM, or the original recommendation if the LLM call fails.
    """
    try:
        # Prepare prompt, including instance_type for EC2 or db_instance_class for RDS
        if resource_type == 'EC2' and instance_type:
            prompt = (
                f"You are an AWS optimization expert. An EC2 instance of type '{instance_type}' "
                f"has triggered the rule '{rule}' with the recommendation: '{recommendation}'. "
                f"Refine this recommendation to provide a concise, actionable suggestion for optimizing the EC2 instance. "
                f"Include specific details about the instance type and rule"
            )
        elif resource_type == 'RDS' and db_instance_class:
            prompt = (
                f"You are an AWS optimization expert. An RDS instance of class '{db_instance_class}' "
                f"has triggered the rule '{rule}' with the recommendation: '{recommendation}'. "
                f"Refine this recommendation to provide a concise, actionable suggestion for optimizing the RDS instance. "
                f"Include specific details about the DB instance class and rule"
            )
        else:
            prompt = (
                f"You are an AWS optimization expert. A {resource_type} resource "
                f"has triggered the rule '{rule}' with the recommendation: '{recommendation}'. "
                f"Refine this recommendation to provide a concise, actionable suggestion for optimizing the {resource_type} resource. "
                f"Include specific details about the rule"
            )
        
        
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"You are a helpful AWS optimization assistant for {resource_type}."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=350,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as llm_error:
        print(f"LLM API error for {resource_type} {resource_id}: {str(llm_error)}")
        return recommendation  

# @tool
# def get_recommendations_for_all_metrics(config: RunnableConfig) -> str:
#     """
#     Fetches metrics for a given user_id, compares them with cost table rules,
#     and returns recommendations for all resource types (EC2, S3, RDS, Lambda) as a formatted string.
#     For all resources, recommendations are passed to an LLM for refinement before inclusion in the output.
    
#     Args:
#         config (RunnableConfig): Contains user_id in config['configurable']
    
#     Returns:
#         str: Formatted string containing recommendations or a message if none are found.
#     """
#     user_id = config.get('configurable', {}).get('user_id', 'unknown')
#     try:
#         # Pull in env vars
#         load_dotenv()
#         database_url = os.getenv('DATABASE_URL')
#         openai_api_key = os.getenv('OPENAI_API_KEY')
#         if not database_url:
#             raise ValueError("DATABASE_URL not found in .env file")
#         if not openai_api_key:
#             raise ValueError("OPENAI_API_KEY not found in .env file")

       
#         engine = create_engine(database_url)

        
#         openai_client = OpenAI(api_key=openai_api_key)

#         recommendations = []

#         with engine.connect() as connection:
            
#             metrics_query = text("""
#                 SELECT resource_type, resource_identifier, metrics_data
#                 FROM metrics
#                 WHERE userid = :user_id;
#             """)
#             metrics_result = connection.execute(metrics_query, {"user_id": user_id}).mappings().fetchall()

            
#             cost_query = text("""
#                 SELECT resource_type, rule, recommendation
#                 FROM cost
#             """)
#             cost_result = connection.execute(cost_query).mappings().fetchall()

#             # Organize cost rules by resource_type for easy lookup
#             cost_rules_by_type = {}
#             for row in cost_result:
#                 resource_type = row['resource_type']
#                 if resource_type not in cost_rules_by_type:
#                     cost_rules_by_type[resource_type] = []
#                 cost_rules_by_type[resource_type].append({
#                     'rule': row['rule'],
#                     'recommendation': row['recommendation']
#                 })

#             # Process each metric record
#             for metric in metrics_result:
#                 resource_type = metric['resource_type']
#                 resource_id = metric['resource_identifier']
#                 metrics_data = metric['metrics_data']

#                 # Skip if no rules exist for this resource_type
#                 if resource_type not in cost_rules_by_type:
#                     continue

#                 # Extract relevant metrics based on resource_type
#                 for rule_info in cost_rules_by_type[resource_type]:
#                     rule = rule_info['rule']
#                     recommendation = rule_info['recommendation']

#                     # EC2 rules (AvgCPU, MaxCPU)
#                     if resource_type == 'EC2':
#                         ec2_instance_type = metrics_data.get('InstanceType', 'unknown')
#                         # Handle AvgCPU rules
#                         avg_cpu_match = re.match(r'AvgCPU\s*(>|<)\s*(\d+\.?\d*)', rule)
#                         if avg_cpu_match:
#                             operator, threshold = avg_cpu_match.groups()
#                             threshold = float(threshold)
#                             avg_cpu_str = metrics_data.get('AvgCPU') or \
#                                           metrics_data.get('Metrics', {}).get('CPUUtilization', {}).get('Average', '0%')
#                             try:
#                                 avg_cpu = float(avg_cpu_str.replace('%', ''))
#                                 if (operator == '>' and avg_cpu > threshold) or \
#                                    (operator == '<' and avg_cpu < threshold):
#                                     llm_recommendation = get_llm_recommendation(
#                                         openai_client, resource_type, resource_id, ec2_instance_type, None, rule, recommendation
#                                     )
#                                     recommendations.append({
#                                         'resource_type': resource_type,
#                                         'instance_type': ec2_instance_type,
#                                         'resource_identifier': resource_id,
#                                         'metric': f"AvgCPU: {avg_cpu}%",
#                                         'rule': rule,
#                                         'recommendation': llm_recommendation
#                                     })
#                             except ValueError:
#                                 print(f"Invalid AvgCPU format for {resource_id}: {avg_cpu_str}")

#                         # Handle MaxCPU rules
#                         max_cpu_match = re.match(r'MaxCPU\s*>\s*(\d+\.?\d*)', rule)
#                         if max_cpu_match:
#                             threshold = float(max_cpu_match.group(1))
#                             max_cpu_str = metrics_data.get('MaxCPU') or \
#                                           metrics_data.get('Metrics', {}).get('CPUUtilization', {}).get('Maximum', '0%')
#                             try:
#                                 max_cpu = float(max_cpu_str.replace('%', ''))
#                                 if max_cpu > threshold:
#                                     llm_recommendation = get_llm_recommendation(
#                                         openai_client, resource_type, resource_id, ec2_instance_type, None, rule, recommendation
#                                     )
#                                     recommendations.append({
#                                         'resource_type': resource_type,
#                                         'instance_type': ec2_instance_type,
#                                         'resource_identifier': resource_id,
#                                         'metric': f"MaxCPU: {max_cpu}%",
#                                         'rule': rule,
#                                         'recommendation': llm_recommendation
#                                     })
#                             except ValueError:
#                                 print(f"Invalid MaxCPU format for {resource_id}: {max_cpu_str}")

#                     # RDS rules (AvgCPU, MaxCPU)
#                     elif resource_type == 'RDS':
#                         db_instance_class = metrics_data.get('DBInstanceClass', 'unknown')
#                         # Handle AvgCPU rules
#                         avg_cpu_match = re.match(r'AvgCPU\s*(>|<)\s*(\d+\.?\d*)', rule)
#                         if avg_cpu_match:
#                             operator, threshold = avg_cpu_match.groups()
#                             threshold = float(threshold)
#                             avg_cpu_str = metrics_data.get('AvgCPU') or \
#                                           metrics_data.get('Metrics', {}).get('CPUUtilization', {}).get('Average', '0%')
#                             try:
#                                 avg_cpu = float(avg_cpu_str.replace('%', ''))
#                                 if (operator == '>' and avg_cpu > threshold) or \
#                                    (operator == '<' and avg_cpu < threshold):
#                                     llm_recommendation = get_llm_recommendation(
#                                         openai_client, resource_type, resource_id, None, db_instance_class, rule, recommendation
#                                     )
#                                     recommendations.append({
#                                         'resource_type': resource_type,
#                                         'db_instance_class': db_instance_class,
#                                         'resource_identifier': resource_id,
#                                         'metric': f"AvgCPU: {avg_cpu}%",
#                                         'rule': rule,
#                                         'recommendation': llm_recommendation
#                                     })
#                             except ValueError:
#                                 print(f"Invalid AvgCPU format for {resource_id}: {avg_cpu_str}")

#                         # Handle MaxCPU rules
#                         max_cpu_match = re.match(r'MaxCPU\s*>\s*(\d+\.?\d*)', rule)
#                         if max_cpu_match:
#                             threshold = float(max_cpu_match.group(1))
#                             max_cpu_str = metrics_data.get('MaxCPU') or \
#                                           metrics_data.get('Metrics', {}).get('CPUUtilization', {}).get('Maximum', '0%')
#                             try:
#                                 max_cpu = float(max_cpu_str.replace('%', ''))
#                                 if max_cpu > threshold:
#                                     llm_recommendation = get_llm_recommendation(
#                                         openai_client, resource_type, resource_id, None, db_instance_class, rule, recommendation
#                                     )
#                                     recommendations.append({
#                                         'resource_type': resource_type,
#                                         'db_instance_class': db_instance_class,
#                                         'resource_identifier': resource_id,
#                                         'metric': f"MaxCPU: {max_cpu}%",
#                                         'rule': rule,
#                                         'recommendation': llm_recommendation
#                                     })
#                             except ValueError:
#                                 print(f"Invalid MaxCPU format for {resource_id}: {max_cpu_str}")

#                     # S3 rules (BucketSizeMB, NumberOfObjects)
#                     elif resource_type == 'S3':
#                         metrics = metrics_data.get('Metrics', {})
#                         bucket_size_mb = float(metrics.get('BucketSizeMB', 0))
#                         num_objects = int(metrics.get('NumberOfObjects', 0))

#                         # Handle BucketSizeMB rules
#                         size_match = re.match(r'BucketSizeMB\s*>\s*(\d+\.?\d*)', rule)
#                         if size_match:
#                             threshold = float(size_match.group(1))
#                             if bucket_size_mb > threshold:
#                                 llm_recommendation = get_llm_recommendation(
#                                     openai_client, resource_type, resource_id, None, None, rule, recommendation
#                                 )
#                                 recommendations.append({
#                                     'resource_type': resource_type,
#                                     'resource_identifier': resource_id,
#                                     'metric': f"BucketSizeMB: {bucket_size_mb}",
#                                     'rule': rule,
#                                     'recommendation': llm_recommendation
#                                 })

#                         # Handle NumberOfObjects rules
#                         objects_match = re.match(r'NumberOfObjects\s*>\s*(\d+)', rule)
#                         if objects_match:
#                             threshold = int(objects_match.group(1))
#                             if num_objects > threshold:
#                                 llm_recommendation = get_llm_recommendation(
#                                     openai_client, resource_type, resource_id, None, None, rule, recommendation
#                                 )
#                                 recommendations.append({
#                                     'resource_type': resource_type,
#                                     'resource_identifier': resource_id,
#                                     'metric': f"NumberOfObjects: {num_objects}",
#                                     'rule': rule,
#                                     'recommendation': llm_recommendation
#                                 })

#                         # Handle BucketSizeMB > 100 and low access (simplified, assuming low access not available)
#                         if 'BucketSizeMB > 100 and low access' in rule and bucket_size_mb > 100:
#                             llm_recommendation = get_llm_recommendation(
#                                 openai_client, resource_type, resource_id, None, None, rule, recommendation
#                             )
#                             recommendations.append({
#                                 'resource_type': resource_type,
#                                 'resource_identifier': resource_id,
#                                 'metric': f"BucketSizeMB: {bucket_size_mb} (assuming low access)",
#                                 'rule': rule,
#                                 'recommendation': llm_recommendation
#                             })

#                     # Lambda rules (Errors.Total, Duration.Average, Throttles.Total, Invocations.Total)
#                     elif resource_type == 'Lambda':
#                         metrics = metrics_data.get('Metrics', {})
#                         errors_total = int(metrics.get('Errors', {}).get('Total', 0))
#                         duration_avg_str = str(metrics.get('Duration', {}).get('Average', '0'))
#                         try:
#                             duration_avg = float(re.sub(r'[^\d.]', '', duration_avg_str))
#                         except ValueError:
#                             print(f"Invalid Duration.Average format for {resource_id}: {duration_avg_str}")
#                             duration_avg = 0.0
#                         throttles_total = int(metrics.get('Throttles', {}).get('Total', 0))
#                         invocations_total = int(metrics.get('Invocations', {}).get('Total', 0))

#                         # Handle Errors.Total
#                         errors_match = re.match(r'Errors\.Total\s*>\s*(\d+)', rule)
#                         if errors_match:
#                             threshold = int(errors_match.group(1))
#                             if errors_total > threshold:
#                                 llm_recommendation = get_llm_recommendation(
#                                     openai_client, resource_type, resource_id, None, None, rule, recommendation
#                                 )
#                                 recommendations.append({
#                                     'resource_type': resource_type,
#                                     'resource_identifier': resource_id,
#                                     'metric': f"Errors.Total: {errors_total}",
#                                     'rule': rule,
#                                     'recommendation': llm_recommendation
#                                 })

#                         # Handle Duration.Average
#                         duration_match = re.match(r'Duration\.Average\s*>\s*(\d+\.?\d*)ms', rule)
#                         if duration_match:
#                             threshold = float(duration_match.group(1))
#                             if duration_avg > threshold:
#                                 llm_recommendation = get_llm_recommendation(
#                                     openai_client, resource_type, resource_id, None, None, rule, recommendation
#                                 )
#                                 recommendations.append({
#                                     'resource_type': resource_type,
#                                     'resource_identifier': resource_id,
#                                     'metric': f"Duration.Average: {duration_avg}ms",
#                                     'rule': rule,
#                                     'recommendation': llm_recommendation
#                                 })

#                         # Handle Throttles.Total
#                         throttles_match = re.match(r'Throttles\.Total\s*>\s*(\d+)', rule)
#                         if throttles_match:
#                             threshold = int(throttles_match.group(1))
#                             if throttles_total > threshold:
#                                 llm_recommendation = get_llm_recommendation(
#                                     openai_client, resource_type, resource_id, None, None, rule, recommendation
#                                 )
#                                 recommendations.append({
#                                     'resource_type': resource_type,
#                                     'resource_identifier': resource_id,
#                                     'metric': f"Throttles.Total: {throttles_total}",
#                                     'rule': rule,
#                                     'recommendation': llm_recommendation
#                                 })

#                         # Handle Invocations.Total
#                         invocations_match = re.match(r'Invocations\.Total\s*=\s*(\d+)', rule)
#                         if invocations_match:
#                             threshold = int(invocations_match.group(1))
#                             if invocations_total == threshold:
#                                 llm_recommendation = get_llm_recommendation(
#                                     openai_client, resource_type, resource_id, None, None, rule, recommendation
#                                 )
#                                 recommendations.append({
#                                     'resource_type': resource_type,
#                                     'resource_identifier': resource_id,
#                                     'metric': f"Invocations.Total: {invocations_total}",
#                                     'rule': rule,
#                                     'recommendation': llm_recommendation
#                                 })

#         # Format recommendations as a string
#         if recommendations:
#             output = []
#             for rec in recommendations:
#                 # Include instance_type for EC2, db_instance_class for RDS
#                 if rec['resource_type'] == 'EC2':
#                     output.append(
#                         f"Resource Type: {rec['resource_type']}\n"
#                         f"Instance Type: {rec['instance_type']}\n"
#                         f"Resource: {rec['resource_identifier']}\n"
#                         f"Metric: {rec['metric']}\n"
#                         f"Rule: {rec['rule']}\n"
#                         f"Recommendation: {rec['recommendation']}\n"
#                         f"{'-' * 50}"
#                     )
#                 elif rec['resource_type'] == 'RDS':
#                     output.append(
#                         f"Resource Type: {rec['resource_type']}\n"
#                         f"DB Instance Class: {rec['db_instance_class']}\n"
#                         f"Resource: {rec['resource_identifier']}\n"
#                         f"Metric: {rec['metric']}\n"
#                         f"Rule: {rec['rule']}\n"
#                         f"Recommendation: {rec['recommendation']}\n"
#                         f"{'-' * 50}"
#                     )
#                 else:
#                     output.append(
#                         f"Resource Type: {rec['resource_type']}\n"
#                         f"Resource: {rec['resource_identifier']}\n"
#                         f"Metric: {rec['metric']}\n"
#                         f"Rule: {rec['rule']}\n"
#                         f"Recommendation: {rec['recommendation']}\n"
#                         f"{'-' * 50}"
#                     )
#             return "\n".join(output)
#         else:
#             return f"No recommendations found for user_id={user_id}"

#     except Exception as e:
#         return f"Error: {str(e)}"
@tool
def get_recommendations_for_all_metrics(config: RunnableConfig) -> str:
    """
    Fetches metrics for a given user_id, compares them with cost table rules,
    and returns recommendations for all resource types (EC2, S3, RDS, Lambda) as a formatted string.
    For all resources, recommendations are passed to an LLM for refinement before inclusion in the output.

    Args:
        config (RunnableConfig): Contains user_id in config['configurable']

    Returns:
        str: Formatted string containing recommendations or a message if none are found.
    """
    user_id = config.get('configurable', {}).get('user_id', 'unknown')
    return generate_recommendations_for_metrics(user_id, for_db_insertion=False)

    
def insert_recommendations_to_db(recommendations_list, userid):
    """Insert recommendations into the recommendation table with userid."""
    try:
        # Create a database session
        with SessionLocal() as session:
            try:
                # Process each recommendation
                for rec in recommendations_list:
                    resource_type = rec['resource_type']
                    arn = rec.get('arn', '')  # We need to extract ARN for each recommendation
                    recommendation_text = rec['recommendation']
                    
                    # SQL query to insert or update recommendations
                    query = """
                        INSERT INTO recommendation (
                            userid, resource_type, arn, recommendation_text, updated_timestamp
                        ) VALUES (
                            :userid, :resource_type, :arn, :recommendation_text, CURRENT_TIMESTAMP
                        )
                        ON CONFLICT (userid, resource_type, arn)
                        DO UPDATE SET
                            recommendation_text = EXCLUDED.recommendation_text,
                            updated_timestamp = CURRENT_TIMESTAMP
                    """
                    
                    session.execute(text(query), {
                        'userid': userid,
                        'resource_type': resource_type,
                        'arn': arn,
                        'recommendation_text': recommendation_text
                    })
                
                session.commit()
                logger.info(f"Successfully inserted/updated {len(recommendations_list)} recommendations for userid {userid}")
            
            except Exception as e:
                session.rollback()
                logger.error(f"Error inserting recommendations into database for userid {userid}: {str(e)}")
                raise
    
    except Exception as e:
        logger.error(f"Error in insert_recommendations_to_db for userid {userid}: {str(e)}")
        
def generate_recommendations_for_metrics(user_id, for_db_insertion=False):
    """
    Fetches metrics for a given user_id, compares them with cost table rules,
    and returns recommendations for all resource types (EC2, S3, RDS, Lambda).
    
    Args:
        user_id (str): The user ID to fetch metrics for
        for_db_insertion (bool): Whether this function is being called for DB insertion
    
    Returns:
        list or str: List of recommendation dictionaries if for_db_insertion=True, 
                    otherwise a formatted string for user display
    """
    try:
        # Pull in env vars
        load_dotenv()
        database_url = os.getenv('DATABASE_URL')
        openai_api_key = os.getenv('OPENAI_API_KEY')
        if not database_url:
            raise ValueError("DATABASE_URL not found in .env file")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY not found in .env file")
        
        engine = create_engine(database_url)
        openai_client = OpenAI(api_key=openai_api_key)
        
        recommendations = []
        
        with engine.connect() as connection:
            # Fetch metrics for this user
            metrics_query = text("""
                SELECT resource_type, resource_identifier, metrics_data, arn
                FROM metrics
                WHERE userid = :user_id;
            """)
            metrics_result = connection.execute(metrics_query, {"user_id": user_id}).mappings().fetchall()
            
            # Fetch cost rules
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
                arn = metric['arn']  
                
                # Skip if no rules exist for this resource_type
                if resource_type not in cost_rules_by_type:
                    continue
                
                # Extract relevant metrics based on resource_type
                for rule_info in cost_rules_by_type[resource_type]:
                    rule = rule_info['rule']
                    recommendation = rule_info['recommendation']
                    
                    # EC2 rules (AvgCPU, MaxCPU)
                    if resource_type == 'EC2':
                        ec2_instance_type = metrics_data.get('InstanceType', 'unknown')
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
                                    llm_recommendation = get_llm_recommendation(
                                        openai_client, resource_type, resource_id, ec2_instance_type, None, rule, recommendation
                                    )
                                    recommendations.append({
                                        'resource_type': resource_type,
                                        'instance_type': ec2_instance_type,
                                        'resource_identifier': resource_id,
                                        'metric': f"AvgCPU: {avg_cpu}%",
                                        'rule': rule,
                                        'recommendation': llm_recommendation,
                                        'arn': arn  
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
                                    llm_recommendation = get_llm_recommendation(
                                        openai_client, resource_type, resource_id, ec2_instance_type, None, rule, recommendation
                                    )
                                    recommendations.append({
                                        'resource_type': resource_type,
                                        'instance_type': ec2_instance_type,
                                        'resource_identifier': resource_id,
                                        'metric': f"MaxCPU: {max_cpu}%",
                                        'rule': rule,
                                        'recommendation': llm_recommendation,
                                        'arn': arn  
                                    })
                            except ValueError:
                                print(f"Invalid MaxCPU format for {resource_id}: {max_cpu_str}")
                    
                    # RDS rules (AvgCPU, MaxCPU)
                    elif resource_type == 'RDS':
                        # Similar to EC2 rules but for RDS
                        db_instance_class = metrics_data.get('DBInstanceClass', 'unknown')
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
                                    llm_recommendation = get_llm_recommendation(
                                        openai_client, resource_type, resource_id, None, db_instance_class, rule, recommendation
                                    )
                                    recommendations.append({
                                        'resource_type': resource_type,
                                        'db_instance_class': db_instance_class,
                                        'resource_identifier': resource_id,
                                        'metric': f"AvgCPU: {avg_cpu}%",
                                        'rule': rule,
                                        'recommendation': llm_recommendation,
                                        'arn': arn  
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
                                    llm_recommendation = get_llm_recommendation(
                                        openai_client, resource_type, resource_id, None, db_instance_class, rule, recommendation
                                    )
                                    recommendations.append({
                                        'resource_type': resource_type,
                                        'db_instance_class': db_instance_class,
                                        'resource_identifier': resource_id,
                                        'metric': f"MaxCPU: {max_cpu}%",
                                        'rule': rule,
                                        'recommendation': llm_recommendation,
                                        'arn': arn  
                                    })
                            except ValueError:
                                print(f"Invalid MaxCPU format for {resource_id}: {max_cpu_str}")
                    
                    # S3 rules
                    elif resource_type == 'S3':
                        metrics = metrics_data.get('Metrics', {})
                        bucket_size_mb = float(metrics.get('BucketSizeMB', 0))
                        num_objects = int(metrics.get('NumberOfObjects', 0))
                        
                        # Handle BucketSizeMB rules
                        size_match = re.match(r'BucketSizeMB\s*>\s*(\d+\.?\d*)', rule)
                        if size_match:
                            threshold = float(size_match.group(1))
                            if bucket_size_mb > threshold:
                                llm_recommendation = get_llm_recommendation(
                                    openai_client, resource_type, resource_id, None, None, rule, recommendation
                                )
                                recommendations.append({
                                    'resource_type': resource_type,
                                    'resource_identifier': resource_id,
                                    'metric': f"BucketSizeMB: {bucket_size_mb}",
                                    'rule': rule,
                                    'recommendation': llm_recommendation,
                                    'arn': arn  
                                })
                        
                        # Handle NumberOfObjects rules
                        objects_match = re.match(r'NumberOfObjects\s*>\s*(\d+)', rule)
                        if objects_match:
                            threshold = int(objects_match.group(1))
                            if num_objects > threshold:
                                llm_recommendation = get_llm_recommendation(
                                    openai_client, resource_type, resource_id, None, None, rule, recommendation
                                )
                                recommendations.append({
                                    'resource_type': resource_type,
                                    'resource_identifier': resource_id,
                                    'metric': f"NumberOfObjects: {num_objects}",
                                    'rule': rule,
                                    'recommendation': llm_recommendation,
                                    'arn': arn  
                                })
                        
                        # Handle BucketSizeMB > 100 and low access
                        if 'BucketSizeMB > 100 and low access' in rule and bucket_size_mb > 100:
                            llm_recommendation = get_llm_recommendation(
                                openai_client, resource_type, resource_id, None, None, rule, recommendation
                            )
                            recommendations.append({
                                'resource_type': resource_type,
                                'resource_identifier': resource_id,
                                'metric': f"BucketSizeMB: {bucket_size_mb} (assuming low access)",
                                'rule': rule,
                                'recommendation': llm_recommendation,
                                'arn': arn  
                            })
                    
                    # Lambda rules
                    elif resource_type == 'Lambda':
                        metrics = metrics_data.get('Metrics', {})
                        errors_total = int(metrics.get('Errors', {}).get('Total', 0))
                        duration_avg_str = str(metrics.get('Duration', {}).get('Average', '0'))
                        try:
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
                                llm_recommendation = get_llm_recommendation(
                                    openai_client, resource_type, resource_id, None, None, rule, recommendation
                                )
                                recommendations.append({
                                    'resource_type': resource_type,
                                    'resource_identifier': resource_id,
                                    'metric': f"Errors.Total: {errors_total}",
                                    'rule': rule,
                                    'recommendation': llm_recommendation,
                                    'arn': arn  
                                })
                        
                        # Handle Duration.Average
                        duration_match = re.match(r'Duration\.Average\s*>\s*(\d+\.?\d*)ms', rule)
                        if duration_match:
                            threshold = float(duration_match.group(1))
                            if duration_avg > threshold:
                                llm_recommendation = get_llm_recommendation(
                                    openai_client, resource_type, resource_id, None, None, rule, recommendation
                                )
                                recommendations.append({
                                    'resource_type': resource_type,
                                    'resource_identifier': resource_id,
                                    'metric': f"Duration.Average: {duration_avg}ms",
                                    'rule': rule,
                                    'recommendation': llm_recommendation,
                                    'arn': arn  
                                })
                        
                        # Handle Throttles.Total
                        throttles_match = re.match(r'Throttles\.Total\s*>\s*(\d+)', rule)
                        if throttles_match:
                            threshold = int(throttles_match.group(1))
                            if throttles_total > threshold:
                                llm_recommendation = get_llm_recommendation(
                                    openai_client, resource_type, resource_id, None, None, rule, recommendation
                                )
                                recommendations.append({
                                    'resource_type': resource_type,
                                    'resource_identifier': resource_id,
                                    'metric': f"Throttles.Total: {throttles_total}",
                                    'rule': rule,
                                    'recommendation': llm_recommendation,
                                    'arn': arn  
                                })
                        
                        # Handle Invocations.Total
                        invocations_match = re.match(r'Invocations\.Total\s*=\s*(\d+)', rule)
                        if invocations_match:
                            threshold = int(invocations_match.group(1))
                            if invocations_total == threshold:
                                llm_recommendation = get_llm_recommendation(
                                    openai_client, resource_type, resource_id, None, None, rule, recommendation
                                )
                                recommendations.append({
                                    'resource_type': resource_type,
                                    'resource_identifier': resource_id,
                                    'metric': f"Invocations.Total: {invocations_total}",
                                    'rule': rule,
                                    'recommendation': llm_recommendation,
                                    'arn': arn  # Include ARN for database insertion
                                })
        
        # If for DB insertion, return list of recommendation dictionaries
        if for_db_insertion:
            return recommendations
        
        # Otherwise format recommendations as a string for user display
        if recommendations:
            output = []
            for rec in recommendations:
                # Include instance_type for EC2, db_instance_class for RDS
                if rec['resource_type'] == 'EC2':
                    output.append(
                        f"Resource Type: {rec['resource_type']}\n"
                        f"Instance Type: {rec['instance_type']}\n"
                        f"Resource: {rec['resource_identifier']}\n"
                        f"Metric: {rec['metric']}\n"
                        f"Rule: {rec['rule']}\n"
                        f"Recommendation: {rec['recommendation']}\n"
                        f"{'-' * 50}"
                    )
                elif rec['resource_type'] == 'RDS':
                    output.append(
                        f"Resource Type: {rec['resource_type']}\n"
                        f"DB Instance Class: {rec['db_instance_class']}\n"
                        f"Resource: {rec['resource_identifier']}\n"
                        f"Metric: {rec['metric']}\n"
                        f"Rule: {rec['rule']}\n"
                        f"Recommendation: {rec['recommendation']}\n"
                        f"{'-' * 50}"
                    )
                else:
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
        error_msg = f"Error generating recommendations: {str(e)}"
        logger.error(error_msg)
        if for_db_insertion:
            return []
        else:
            return error_msg

def collect_metrics_for_user(userid, access_key, secret_key, region, output_file):
    """Collect metrics for a single user and return True if successful"""
    try:
        print(f"Collecting metrics for userid {userid} in region {region}")
        
        # Initialize AWSMetricsCollector and collect metrics
        collector = AWSMetricsCollector(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        
        logger.info(f"Running metrics collection for userid {userid}")
        metrics_data = collector.run_collection()
        
        # Save metrics to JSON file (optional)
        print(f"Saving metrics to {output_file} for userid {userid}")
        with open(f"{userid}_{output_file}", 'w') as f:
            json.dump({
                'generatedAt': datetime.datetime.now().isoformat(),
                'metrics': metrics_data,
                'userid': userid
            }, f, indent=2)
        
        # Insert metrics into database
        logger.info(f"Inserting metrics into database for userid {userid}")
        insert_metrics_to_db(metrics_data, userid)
        
        print(f"Metrics collection completed for userid {userid}")
        return True
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'InvalidClientTokenId':
            logger.error(f"Invalid AWS credentials for userid {userid}: {str(e)}")
            print(f"Skipping userid {userid} due to invalid credentials")
        else:
            logger.error(f"AWS error for userid {userid}: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Error collecting metrics for userid {userid}: {str(e)}", exc_info=True)
        print(f"Skipping userid {userid} due to error: {str(e)}")
        return False
    
def process_recommendations_for_user(userid):
    """Generate and save recommendations for a single user"""
    try:
        print(f"Generating recommendations for userid {userid}")
        
        # Generate recommendations for this user
        recommendations = generate_recommendations_for_metrics(userid, for_db_insertion=True)
        
        if recommendations:
            # Insert recommendations into the database
            print(f"Saving {len(recommendations)} recommendations to database for userid {userid}")
            insert_recommendations_to_db(recommendations, userid)
            return True
        else:
            print(f"No recommendations generated for userid {userid}")
            return False
            
    except Exception as e:
        logger.error(f"Error processing recommendations for userid {userid}: {str(e)}", exc_info=True)
        return False