from app.database import SessionLocal
from app.models.infrastructure_inventory import InfrastructureInventory
from app.db.metrics_collector import create_or_update_metrics,fetch_all_collected_metrics
from app.database import SessionLocal

from app.db.recommendation import insert_or_update
# from openai import OpenAI
from statistics import mean
import os
from dotenv import load_dotenv

load_dotenv()
# openai.api_key = os.getenv("OPENAI_API_KEY")

from collections import defaultdict

from app.db.connection import get_user_connections_by_type
from app.core.existing_to_tf import get_aws_credentials_from_db
from botocore.exceptions import ClientError


import re
from datetime import datetime, timedelta
from pathlib import Path
import boto3
import json



REGION_NAME_MAP = {
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)",
    "eu-west-1": "EU (Ireland)",
    "eu-central-1": "EU (Frankfurt)",
    "ap-south-1": "Asia Pacific (Mumbai)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "sa-east-1": "South America (São Paulo)",
    # Add more if needed
}
INSTANCE_DOWNSIZE_MAP = {
    # T3 family
    "t3.2xlarge": "t3.xlarge",
    "t3.xlarge": "t3.large",
    "t3.large": "t3.medium",
    "t3.medium": "t3.small",
    "t3.small": "t3.micro",
    "t3.micro": "t3.nano",

    # T2 family
    "t2.2xlarge": "t2.xlarge",
    "t2.xlarge": "t2.large",
    "t2.large": "t2.medium",
    "t2.medium": "t2.small",
    "t2.small": "t2.micro",
    "t2.micro": "t3.nano",        # ✅ cross-family cheaper alternative
    "t2.nano": "t3.nano",         # ✅ cheaper ARM-based alternative

    # M5 family
    "m5.24xlarge": "m5.12xlarge",
    "m5.12xlarge": "m5.4xlarge",
    "m5.4xlarge": "m5.2xlarge",
    "m5.2xlarge": "m5.xlarge",
    "m5.xlarge": "m5.large",
    "m5.large": "t3.large",       # ✅ cost-effective general purpose

    # M4 family
    "m4.16xlarge": "m4.10xlarge",
    "m4.10xlarge": "m4.4xlarge",
    "m4.4xlarge": "m4.2xlarge",
    "m4.2xlarge": "m4.xlarge",
    "m4.xlarge": "m4.large",
    "m4.large": "t3.medium",      # ✅ modern alternative

    # C5 family
    "c5.24xlarge": "c5.12xlarge",
    "c5.12xlarge": "c5.4xlarge",
    "c5.4xlarge": "c5.2xlarge",
    "c5.2xlarge": "c5.xlarge",
    "c5.xlarge": "c5.large",
    "c5.large": "t3.medium",      # ✅ if CPU not fully utilized

    # T4g family (ARM)
    "t4g.large": "t4g.medium",
    "t4g.medium": "t4g.small",
    "t4g.small": "t4g.micro",
    "t4g.micro": "t4g.nano"
}


INSTANCE_UPSIZE_MAP = {
    # T3 family
    "t3.nano": "t3.micro",
    "t3.micro": "t3.small",
    "t3.small": "t3.medium",
    "t3.medium": "t3.large",
    "t3.large": "t3.xlarge",
    "t3.xlarge": "t3.2xlarge",

    # T2 family
    "t2.nano": "t2.micro",
    "t2.micro": "t2.small",
    "t2.small": "t2.medium",
    "t2.medium": "t2.large",
    "t2.large": "t2.xlarge",
    "t2.xlarge": "t2.2xlarge",

    # M5 family
    "m5.large": "m5.xlarge",
    "m5.xlarge": "m5.2xlarge",
    "m5.2xlarge": "m5.4xlarge",
    "m5.4xlarge": "m5.12xlarge",
    "m5.12xlarge": "m5.24xlarge",

    # C5 family
    "c5.large": "c5.xlarge",
    "c5.xlarge": "c5.2xlarge",
    "c5.2xlarge": "c5.4xlarge",
    "c5.4xlarge": "c5.12xlarge",
    "c5.12xlarge": "c5.24xlarge",

    # T4g family
    "t4g.nano": "t4g.micro",
    "t4g.micro": "t4g.small",
    "t4g.small": "t4g.medium",
    "t4g.medium": "t4g.large",

    # Extra cross-family upsize
    "t3.nano": "t4g.micro",        
    "t2.nano": "t3.micro",         
    "t2.micro": "t3.small",
}






from openai import OpenAI

api_key = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=api_key)

def generate_llm_recommendation(instance_type, suggested_instance, cost_hourly, cost_saving, percent_saving):
    prompt = f"""
You are a cloud cost optimization advisor.

The current AWS EC2 instance is:
- Type: {instance_type}

Suggested new instance type:
- {suggested_instance}
- New hourly cost: ${cost_hourly:.4f}
- Annual cost savings: ${cost_saving:.2f} ({percent_saving:.1f}%)

Generate a recommendation divided into:
1. Action: What change to make
2. Impact: Why this helps
3. Savings: The cost benefit

Be concise and clear.
Do not include any emojis and all.
"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You're a cloud cost optimization advisor."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=5000,
            temperature=0.5
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"❌ LLM Error: {e}")
        return f"⚠️ Unable to generate LLM recommendation: {e}"





def get_location_from_region(region_code: str, pricing_client=None) -> str:
    """
    Maps AWS region codes to human-readable location names.
    Optionally uses pricing_client for dynamic lookup (not required here).
    """
    return REGION_NAME_MAP.get(region_code, "US East (N. Virginia)")




def get_instance_hourly_price(instance_info: dict) -> float:
    """
    Takes additional_info dict from describe_aws_resource() and returns the hourly price of the instance.

    Args:
        instance_info (dict): Output from describe_aws_resource

    Returns:
        float: Hourly price in USD, or -1.0 if not found or invalid
    """
    try:
        # Required fields from instance_info
        instance_type = instance_info.get("instance_type")
        location = instance_info.get("location", "US East (N. Virginia)")
        operating_system = instance_info.get("operatingSystem", "Linux")
        pre_installed = instance_info.get("preInstalledSw", "NA")
        tenancy = instance_info.get("tenancy", "default")
        capacity_status = instance_info.get("capacitystatus", "Used")

        if not instance_type or not location:
            print("❌ Missing instance_type or location for pricing.")
            return -1.0

        if tenancy == "default":
            tenancy = "Shared"

        # Show query input to debug failures
        print("\n🔎 Pricing Query Params:")
        print(f"  Instance Type: {instance_type}")
        print(f"  Location: {location}")
        print(f"  OS: {operating_system}")
        print(f"  Preinstalled SW: {pre_installed}")
        print(f"  Tenancy: {tenancy}")
        print(f"  Capacity Status: {capacity_status}")

        client = boto3.client("pricing", region_name="us-east-1")

        filters = [
            {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
            {"Type": "TERM_MATCH", "Field": "location", "Value": location},
            {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": operating_system},
            {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": pre_installed},
            {"Type": "TERM_MATCH", "Field": "tenancy", "Value": tenancy},
            {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": capacity_status}
        ]

        # Initial pricing call
        response = client.get_products(
            ServiceCode="AmazonEC2",
            Filters=filters,
            MaxResults=1
        )

        # If empty, try fallback (without capacitystatus)
        if not response["PriceList"]:
            print("⚠️ No pricing data with capacitystatus, retrying without it...")
            fallback_filters = [f for f in filters if f["Field"] != "capacitystatus"]
            response = client.get_products(
                ServiceCode="AmazonEC2",
                Filters=fallback_filters,
                MaxResults=1
            )

        if not response["PriceList"]:
            print(f"❌ Still no pricing found for {instance_type} in {location}")
            return -1.0

        price_item = json.loads(response["PriceList"][0])
        terms = price_item.get("terms", {}).get("OnDemand", {})
        for term_id, term in terms.items():
            price_dimensions = term.get("priceDimensions", {})
            for dim_id, dim in price_dimensions.items():
                price = float(dim["pricePerUnit"]["USD"])
                return price

        print(f"⚠️ Pricing info not found in 'terms' block.")
        return -1.0

    except Exception as e:
        print(f"❌ Failed to fetch pricing for instance: {e}")
        return -1.0



def describe_aws_resource(user_id: int, arn: str, service: str, region: str) -> dict:
    from app.core.existing_to_tf import get_aws_credentials_from_db
    from botocore.exceptions import ClientError

    db = SessionLocal()

    # ✅ Get credentials safely
    access_key, secret_key = get_aws_credentials_from_db(user_id)
    db.close()

    if not access_key or not secret_key:
        print(f"⚠️ Missing AWS credentials for user {user_id}")
        return {}

    try:
        session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )

        if service == "EC2":
            match = re.search(r"instance/(i-[a-zA-Z0-9]+)", arn)
            if not match:
                print(f"⚠️ Could not extract instance ID from ARN: {arn}")
                return {}

            instance_id = match.group(1)
            ec2 = session.client("ec2")

            try:
                response = ec2.describe_instances(InstanceIds=[instance_id])
                reservations = response.get("Reservations", [])
                if not reservations or not reservations[0].get("Instances"):
                    print(f"⚠️ Instance not found or unavailable for ARN: {arn}")
                    return {}

                instance = reservations[0]["Instances"][0]

            except ClientError as e:
                print(f"❌ AWS describe error for {arn}: {e}")
                return {}

            instance_type = instance.get("InstanceType")
            tenancy = instance.get("Placement", {}).get("Tenancy", "default")
            launch_time = str(instance.get("LaunchTime"))
            platform_details = instance.get("PlatformDetails", "Linux/UNIX")
            operating_system = "Linux"
            if "Windows" in platform_details:
                operating_system = "Windows"

            pricing = session.client("pricing", region_name="us-east-1")
            location_name = get_location_from_region(region, pricing)

            return {
                "instance_id": instance_id,
                "instance_type": instance_type,
                "availability_zone": instance.get("Placement", {}).get("AvailabilityZone"),
                "launch_time": launch_time,
                "region_code": region,
                "location": location_name,
                "tenancy": tenancy,
                "operatingSystem": operating_system,
                "preInstalledSw": "NA",
                "capacitystatus": "Used"
            }

        # Other AWS services can be handled similarly here
        return {}

    except Exception as e:
        print(f"❌ Unexpected error during AWS resource description: {e}")
        return {}




def fetch_arns_grouped_by_user_id():
    session = SessionLocal()
    try:
        result = defaultdict(list)
        records = session.query(InfrastructureInventory.user_id, InfrastructureInventory.arn).all()
        for user_id, arn in records:
            result[user_id].append(arn)
        return dict(result)
    finally:
        session.close()



def load_metric_config(config_path="cloudwatch_metrics_config.json"):
    with open(config_path, "r") as f:
        return json.load(f)

def get_cloudwatch_client(region="us-east-1"):
    return boto3.client("cloudwatch", region_name=region)

def extract_service_and_dimensions(arn, config):
    for service, details in config.items():
        pattern = re.compile(details["ArnPattern"])
        match = pattern.match(arn)
        if match:
            return service, match.groupdict()
    return None, None

def fetch_metrics_for_arn(cw, namespace, metric_name, dimensions, statistics, period, days=14):
    now = datetime.utcnow()
    start_time = now - timedelta(days=days)

    response = cw.get_metric_statistics(
        Namespace=namespace,
        MetricName=metric_name,
        Dimensions=[{"Name": k, "Value": v} for k, v in dimensions.items()],
        StartTime=start_time,
        EndTime=now,
        Period=period,
        Statistics=statistics
    )
    datapoints = response.get("Datapoints", [])
    return sorted(datapoints, key=lambda x: x["Timestamp"])


def collect_all_metrics(arns_by_user, config_path="app\\core\\cloudwatch_metrics_config.json", output_path="cloudwatch_metrics_output.json"):
    config = load_metric_config(config_path)
    results = {}
    db = SessionLocal()

    try:
        for user_id, arns in arns_by_user.items():
            results[user_id] = {}
            for arn in arns:
                service, dim_values = extract_service_and_dimensions(arn, config)
                if not service:
                    continue  # Skip unknown services

                service_conf = config[service]
                results[user_id][arn] = {}
                region_match = re.search(r"arn:aws:[^:]+:([^:]*):", arn)
                region = region_match.group(1) if region_match and region_match.group(1) else "us-east-1"
                cw = get_cloudwatch_client(region)

                metric_result = {}
                for metric in service_conf["metrics"]:
                    dim_keys = metric["Dimensions"]
                    try:
                        dimensions = {key: dim_values[key] for key in dim_keys}
                    except KeyError:
                        continue  # Missing required dimension keys

                    datapoints = fetch_metrics_for_arn(
                        cw,
                        metric["Namespace"],
                        metric["MetricName"],
                        dimensions,
                        metric["Statistics"],
                        metric["Period"],
                        days=14
                    )

                    metric_result[metric["MetricName"]] = datapoints
                    results[user_id][arn][metric["MetricName"]] = datapoints

                # 🔄 Insert into DB
                if metric_result:
                    # 🔍 Fetch additional info from AWS
                    additional_info = describe_aws_resource(
                        user_id=user_id,
                        arn=arn,
                        service=service,
                        region=region
                    )
                    if additional_info and service == "EC2":
                        hourly_price = get_instance_hourly_price(additional_info)
                        instance_type = additional_info.get("instance_type", "unknown")
                        print(f"💲 Instance Type: {instance_type}, Hourly Price: ${hourly_price:.4f}")
                    # 🔄 Insert with extra info
                    create_or_update_metrics(
                        db=db,
                        userid=user_id,
                        arn=arn,
                        resource_type=service,
                        metrics_data=metric_result,
                        additional_info=additional_info
                    )


        # Save to file (optional reporting/logging)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2, default=str)

        print(f"✅ Metrics saved to DB and JSON: {output_path}")
        return results

    finally:
        db.close()


from statistics import mean

def load_recommendation_rules(path="app\core\cloudwatch_recommendation_rules.json"):
    with open(path, "r") as f:
        return json.load(f)

def evaluate_condition(stat_value, condition_str):
    try:
        if condition_str.endswith("%"):
            condition_str = condition_str.replace("%", "")
            stat_value *= 100  # Normalize to percentage
        if ">=" in condition_str:
            return stat_value >= float(condition_str.split(">=")[-1])
        elif "<=" in condition_str:
            return stat_value <= float(condition_str.split("<=")[-1])
        elif ">" in condition_str:
            return stat_value > float(condition_str.split(">")[-1])
        elif "<" in condition_str:
            return stat_value < float(condition_str.split("<")[-1])
        elif "==" in condition_str:
            return stat_value == float(condition_str.split("==")[-1])
        return False
    except Exception as e:
        print(f"❌ Error evaluating condition: {condition_str} on value {stat_value}: {e}")
        return False

def generate_recommendations():
    db = SessionLocal()
    metrics_data = fetch_all_collected_metrics(db)
    db.close()

    rules = load_recommendation_rules()
    recommendations = []

    for record in metrics_data:
        resource_type = record["resource_type"]
        metrics = record["metrics_data"]
        userid = record["userid"]
        arn = record["arn"]

        if resource_type != "EC2":
            continue

        additional_info = describe_aws_resource(userid, arn, "EC2", record.get("metrics_data", {}).get("region_code", "us-east-1"))
        if not additional_info:
            continue

        current_instance = additional_info.get("instance_type")
        current_hourly_price = get_instance_hourly_price(additional_info)
        if current_hourly_price == -1:
            continue

        for metric_name, datapoints in metrics.items():
            if metric_name not in rules.get(resource_type, {}):
                continue

            for rule in rules[resource_type][metric_name]:
                stat_type = rule["stat"]
                stat_values = [dp.get(stat_type) for dp in datapoints if dp.get(stat_type) is not None]

                if not stat_values:
                    continue

                avg_stat_value = mean(stat_values)
                if evaluate_condition(avg_stat_value, rule["condition"]):
                    action = rule["recommendation"]
                    suggested_instance = None

                    if action == "Downsize":
                        suggested_instance = INSTANCE_DOWNSIZE_MAP.get(current_instance)
                    elif action == "Upgrade":
                        suggested_instance = INSTANCE_UPSIZE_MAP.get(current_instance)

                    if suggested_instance:
                        # Create mock additional_info to price suggestion
                        mock_info = additional_info.copy()
                        mock_info["instance_type"] = suggested_instance
                        new_hourly_price = get_instance_hourly_price(mock_info)

                        if new_hourly_price > 0:
                            current_annual = current_hourly_price * 24 * 365
                            new_annual = new_hourly_price * 24 * 365
                            delta = current_annual - new_annual
                            delta_percent = abs((delta / current_annual) * 100)

                            cost_impact = (
                                f"💰 Annual Cost Impact: "
                                f"{'Savings' if delta > 0 else 'Increase'} of ${abs(delta):.2f} ({delta_percent:.1f}%)"
                            )

                            # 🔗 LLM call
                            llm_text = generate_llm_recommendation(
                                instance_type=current_instance,
                                suggested_instance=suggested_instance,
                                cost_hourly=new_hourly_price,
                                cost_saving=abs(delta),
                                percent_saving=delta_percent
                            )
                        else:
                            suggested_instance = None
                            cost_impact = "⚠️ Suggested instance pricing unavailable."
                            llm_text = f"{action} recommended for instance {current_instance}, but price lookup failed."
                    else:
                        cost_impact = "ℹ️ No matching size recommendation found."
                        llm_text = f"{action} is recommended but no alternative instance type found."

                    full_recommendation = (
                        f"📊 Metric: {metric_name} ({stat_type}) = {round(avg_stat_value, 2)}\n"
                        f"💡 Recommendation: {action}\n"
                        f"💻 Current Instance: {current_instance} @ ${current_hourly_price:.4f}/hr\n"
                    )

                    if suggested_instance:
                        full_recommendation += (
                            f"⚙️  Suggested Instance: {suggested_instance} @ ${new_hourly_price:.4f}/hr\n"
                            f"{cost_impact}\n\n{llm_text}"
                        )
                    else:
                        full_recommendation += f"{cost_impact}"

                    # DB Save
                    db_rec = SessionLocal()
                    insert_or_update(
                        db=db_rec,
                        userid=userid,
                        resource_type=resource_type,
                        arn=arn,
                        recommendation_text=full_recommendation
                    )
                    db_rec.close()

                    # Console output
                    print(f"\n🔍 [User {userid}] Resource: {arn}")
                    print(full_recommendation)

                    recommendations.append({
                        "userid": userid,
                        "arn": arn,
                        "resource_type": resource_type,
                        "metric": metric_name,
                        "stat_type": stat_type,
                        "average_value": round(avg_stat_value, 2),
                        "recommendation": full_recommendation
                    })

    return recommendations



# Example usage
if __name__ == "__main__":
    arns_by_user = fetch_arns_grouped_by_user_id()
    collect_all_metrics(arns_by_user)
    generate_recommendations()
