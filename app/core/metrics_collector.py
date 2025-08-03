import os
import re
import json
from datetime import datetime, timedelta
from collections import defaultdict
from statistics import mean

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from openai import OpenAI

# --- Database Imports (assuming they are correctly set up) ---
from app.database import SessionLocal
from app.models.infrastructure_inventory import InfrastructureInventory
from app.db.metrics_collector import create_or_update_metrics, fetch_all_collected_metrics
from app.db.recommendation import insert_or_update
from app.core.existing_to_tf import get_aws_credentials_from_db

# --- Load Environment Variables ---
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")
if openai_api_key:
    openai_client = OpenAI(api_key=openai_api_key)
else:
    print("⚠️ OpenAI API key not found. LLM recommendations will be disabled.")
    openai_client = None

# --- Configuration & Mappings ---

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
}

# --- Enhanced EC2 Instance Sizing Maps ---
INSTANCE_DOWNSIZE_MAP = {
    # T3 Family (Intel)
    "t3.2xlarge": "t3.xlarge", "t3.xlarge": "t3.large", "t3.large": "t3.medium",
    "t3.medium": "t3.small", "t3.small": "t3.micro", "t3.micro": "t3.nano",
    # T2 Family (Older Intel) -> Downgrade to modern T3 or T4g
    "t2.2xlarge": "t2.xlarge", "t2.xlarge": "t2.large", "t2.large": "t2.medium",
    "t2.medium": "t2.small", "t2.small": "t2.micro", "t2.micro": "t3.nano", "t2.nano": "t4g.nano",
    # M5 Family (Intel General Purpose) -> Downgrade to T3 for less demanding workloads
    "m5.24xlarge": "m5.12xlarge", "m5.12xlarge": "m5.4xlarge", "m5.4xlarge": "m5.2xlarge",
    "m5.2xlarge": "m5.xlarge", "m5.xlarge": "m5.large", "m5.large": "t3.large",
    # M4 Family (Older Intel) -> Downgrade to modern T3
    "m4.4xlarge": "m4.2xlarge", "m4.2xlarge": "m4.xlarge", "m4.xlarge": "m4.large", "m4.large": "t3.medium",
    # C5 Family (Intel Compute Optimized) -> Downgrade to T3 if CPU is underutilized
    "c5.24xlarge": "c5.12xlarge", "c5.12xlarge": "c5.4xlarge", "c5.4xlarge": "c5.2xlarge",
    "c5.2xlarge": "c5.xlarge", "c5.xlarge": "c5.large", "c5.large": "t3.medium",
    # T4g Family (ARM/Graviton2)
    "t4g.2xlarge": "t4g.xlarge", "t4g.xlarge": "t4g.large", "t4g.large": "t4g.medium",
    "t4g.medium": "t4g.small", "t4g.small": "t4g.micro", "t4g.micro": "t4g.nano",
}

INSTANCE_UPSIZE_MAP = {
    # T3 Family (Intel)
    "t3.nano": "t3.micro", "t3.micro": "t3.small", "t3.small": "t3.medium",
    "t3.medium": "t3.large", "t3.large": "t3.xlarge", "t3.xlarge": "t3.2xlarge",
    # T2 Family (Older Intel) -> Upgrade to modern T3 or cost-effective T4g
    "t2.nano": "t3.nano", "t2.micro": "t3.micro", "t2.small": "t3.small",
    "t2.medium": "t3.medium", "t2.large": "t3.large", "t2.xlarge": "t3.xlarge", "t2.2xlarge": "t3.2xlarge",
    # M5 Family (Intel General Purpose)
    "m5.large": "m5.xlarge", "m5.xlarge": "m5.2xlarge", "m5.2xlarge": "m5.4xlarge",
    "m5.4xlarge": "m5.12xlarge", "m5.12xlarge": "m5.24xlarge",
    # C5 Family (Intel Compute Optimized)
    "c5.large": "c5.xlarge", "c5.xlarge": "c5.2xlarge", "c5.2xlarge": "c5.4xlarge",
    "c5.4xlarge": "c5.12xlarge", "c5.12xlarge": "c5.24xlarge",
    # T4g Family (ARM/Graviton2)
    "t4g.nano": "t4g.micro", "t4g.micro": "t4g.small", "t4g.small": "t4g.medium",
    "t4g.medium": "t4g.large", "t4g.large": "t4g.xlarge", "t4g.xlarge": "t4g.2xlarge",
    # Cross-family upgrades for cost-performance
    "t3.large": "m5.large", # Move to general purpose for sustained load
    "t3.2xlarge": "m5.2xlarge",
}


# --- Enhanced RDS Instance Sizing Maps ---
RDS_INSTANCE_DOWNSIZE_MAP = {
    # db.t3 (Intel Burstable)
    "db.t3.2xlarge": "db.t3.xlarge", "db.t3.xlarge": "db.t3.large", "db.t3.large": "db.t3.medium",
    "db.t3.medium": "db.t3.small", "db.t3.small": "db.t3.micro",
    # db.m5 (Intel General Purpose) -> Downgrade to db.t3 for less demanding workloads
    "db.m5.24xlarge": "db.m5.12xlarge", "db.m5.12xlarge": "db.m5.8xlarge", "db.m5.8xlarge": "db.m5.4xlarge",
    "db.m5.4xlarge": "db.m5.2xlarge", "db.m5.2xlarge": "db.m5.xlarge", "db.m5.xlarge": "db.m5.large", "db.m5.large": "db.t3.large",
    # db.m4 (Older Intel) -> Downgrade to modern db.m5
    "db.m4.16xlarge": "db.m4.10xlarge", "db.m4.10xlarge": "db.m4.4xlarge", "db.m4.4xlarge": "db.m4.2xlarge",
    "db.m4.2xlarge": "db.m4.xlarge", "db.m4.xlarge": "db.m4.large", "db.m4.large": "db.m5.large",
    # db.r5 (Intel Memory Optimized) -> Downgrade to db.m5 if memory is underutilized
    "db.r5.24xlarge": "db.r5.12xlarge", "db.r5.12xlarge": "db.r5.4xlarge", "db.r5.4xlarge": "db.r5.2xlarge",
    "db.r5.2xlarge": "db.r5.xlarge", "db.r5.xlarge": "db.r5.large", "db.r5.large": "db.m5.large",
}

RDS_INSTANCE_UPSIZE_MAP = {
    # db.t3 (Intel Burstable) -> Upgrade to db.m5 for sustained performance
    "db.t3.micro": "db.t3.small", "db.t3.small": "db.t3.medium", "db.t3.medium": "db.t3.large",
    "db.t3.large": "db.t3.xlarge", "db.t3.xlarge": "db.t3.2xlarge", "db.t3.2xlarge": "db.m5.xlarge",
    # db.m5 (Intel General Purpose)
    "db.m5.large": "db.m5.xlarge", "db.m5.xlarge": "db.m5.2xlarge", "db.m5.2xlarge": "db.m5.4xlarge",
    "db.m5.4xlarge": "db.m5.8xlarge", "db.m5.8xlarge": "db.m5.12xlarge", "db.m5.12xlarge": "db.m5.24xlarge",
    # db.m4 (Older Intel) -> Upgrade to modern db.m5
    "db.m4.large": "db.m5.large", "db.m4.xlarge": "db.m5.xlarge", "db.m4.2xlarge": "db.m5.2xlarge",
    "db.m4.4xlarge": "db.m5.4xlarge", "db.m4.10xlarge": "db.m5.12xlarge", "db.m4.16xlarge": "db.m5.24xlarge",
    # db.r5 (Intel Memory Optimized)
    "db.r5.large": "db.r5.xlarge", "db.r5.xlarge": "db.r5.2xlarge", "db.r5.2xlarge": "db.r5.4xlarge",
    "db.r5.4xlarge": "db.r5.12xlarge", "db.r5.12xlarge": "db.r5.24xlarge",
}

try:
    with open("app\\core\\rds_pricing.json", 'r') as f:
        RDS_PRICING_DATA = json.load(f)
    print("✅ Successfully loaded rds_pricing.json")
except FileNotFoundError:
    print("❌ rds_pricing.json not found. RDS pricing will not be available.")
    RDS_PRICING_DATA = []
except json.JSONDecodeError:
    print("❌ Error decoding rds_pricing.json. Please check the file format.")
    RDS_PRICING_DATA = []


# --- Core Functions ---

def generate_llm_recommendation(resource_display_name, instance_type, suggested_instance, cost_hourly, cost_saving, percent_saving):
    """Generates a concise recommendation using an LLM."""
    if not openai_client:
        return "⚠️ LLM client not initialized. Cannot generate recommendation."

    prompt = f"""
You are a cloud cost optimization advisor.
The current resource is a {resource_display_name}:
- Type: {instance_type}

A cost-saving change is recommended:
- Suggested New Type: {suggested_instance}
- New Hourly Cost: ${cost_hourly:.4f}
- Estimated Annual Savings: ${cost_saving:.2f} ({percent_saving:.1f}%)

**CRITICAL**
-If the pricing data is not available then do not say i do not have have that data , Generate general action , impact and savings.
-**Do NOT**-use sentence like " but pricing information is not available." this , instead say general sentence based upon previous sentence.

Generate a brief recommendation with these sections:
1. Action: The specific change to make.
2. Impact: Why this change is beneficial.
3. Savings: The financial benefit.

Be concise and clear. Do not use emojis or markdown formatting.
"""
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a cloud cost optimization advisor."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200,
            temperature=0.5
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ LLM Error: {e}")
        return f"⚠️ Unable to generate LLM recommendation: {e}"





def get_location_from_region(region_code: str) -> str:
    """Maps an AWS region code to a human-readable location name."""
    return REGION_NAME_MAP.get(region_code, "US East (N. Virginia)")


def get_resource_hourly_price(service: str, resource_info: dict) -> float:
    """
    Fetches the on-demand hourly price for an AWS resource.
    Uses a local JSON file for RDS and the live Pricing API for EC2.
    """
    instance_type = resource_info.get("instance_type")
    location = resource_info.get("location", "US East (N. Virginia)")

    if not all([service, instance_type, location]):
        print("❌ Missing service, instance_type, or location for pricing.")
        return -1.0

    # --- RDS Pricing from local JSON file ---
    if service == "RDS":
        if not RDS_PRICING_DATA:
            print("⚠️ RDS pricing data not loaded. Cannot fetch RDS price.")
            return -1.0
        
        engine = resource_info.get("engine", "MySQL").lower()
        
        for item in RDS_PRICING_DATA:
            # Normalize engine name for matching (e.g., 'PostgreSQL' contains 'postgres')
            if (item['instanceType'] == instance_type and
                engine in item['databaseEngine'].lower() and
                item['region'] == location and
                'single-az' in item['deploymentOption'].lower()):
                price = item.get('hourlyPriceUSD', -1.0)
                print(f"✅ Found RDS price for {instance_type} in local file: ${price:.4f}/hour")
                return price
        
        print(f"❌ RDS price not found in local file for {instance_type} in {location} with engine {engine}")
        return -1.0

    # --- EC2 Pricing from live API with fallbacks ---
    elif service == "EC2":
        try:
            pricing_client = boto3.client("pricing", region_name="us-east-1")
            base_filters = [
                {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
            ]
            
            initial_filters = base_filters + [
                {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": resource_info.get("operatingSystem", "Linux")},
                {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
                {"Type": "TERM_MATCH", "Field": "tenancy", "Value": resource_info.get("tenancy", "Shared")},
                {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"}
            ]

            print(f"🔎 Fetching EC2 pricing for {instance_type} in {location}")
            response = pricing_client.get_products(ServiceCode="AmazonEC2", Filters=initial_filters, MaxResults=1)

            if not response.get("PriceList"):
                print(f"⚠️ No pricing data with 'capacitystatus' for {instance_type}. Retrying without it...")
                fallback_filters_1 = [f for f in initial_filters if f["Field"] != "capacitystatus"]
                response = pricing_client.get_products(ServiceCode="AmazonEC2", Filters=fallback_filters_1, MaxResults=1)

            if not response.get("PriceList"):
                print(f"⚠️ Still no pricing data. Retrying without 'preInstalledSw' as well...")
                fallback_filters_2 = [f for f in initial_filters if f["Field"] not in ["capacitystatus", "preInstalledSw"]]
                response = pricing_client.get_products(ServiceCode="AmazonEC2", Filters=fallback_filters_2, MaxResults=1)
                
            if not response.get("PriceList"):
                print(f"⚠️ Last resort. Retrying with only location and instance type for {instance_type}...")
                response = pricing_client.get_products(ServiceCode="AmazonEC2", Filters=base_filters, MaxResults=1)

            if not response.get("PriceList"):
                print(f"❌ All fallbacks failed. No pricing data found for {instance_type} in {location}.")
                return -1.0

            price_item = json.loads(response["PriceList"][0])
            terms = price_item.get("terms", {}).get("OnDemand", {})
            for term in terms.values():
                for dim in term.get("priceDimensions", {}).values():
                    price = float(dim["pricePerUnit"]["USD"])
                    print(f"✅ Found EC2 price for {instance_type}: ${price:.4f}/hour")
                    return price

            print(f"⚠️ Price dimensions not found for {instance_type}.")
            return -1.0

        except Exception as e:
            print(f"❌ Failed to fetch EC2 pricing for {instance_type}: {e}")
            return -1.0
    
    else:
        print(f"⚠️ Pricing not implemented for service: {service}")
        return -1.0

def describe_aws_resource(user_id: int, arn: str, service: str, region: str) -> dict:
    """
    Describes an AWS resource (EC2 or RDS) and returns its key attributes.
    """
    access_key, secret_key = get_aws_credentials_from_db(user_id)
    if not access_key or not secret_key:
        print(f"⚠️ Missing AWS credentials for user {user_id}")
        return {}

    try:
        session = boto3.Session(aws_access_key_id=access_key, aws_secret_access_key=secret_key, region_name=region)
        location_name = get_location_from_region(region)

        if service == "EC2":
            match = re.search(r"instance/(i-[a-zA-Z0-9]+)", arn)
            if not match: return {}
            instance_id = match.group(1)
            ec2 = session.client("ec2")
            response = ec2.describe_instances(InstanceIds=[instance_id])
            instance = response["Reservations"][0]["Instances"][0]
            
            platform = instance.get("PlatformDetails", "Linux/UNIX")
            os_type = "Windows" if "Windows" in platform else "Linux"

            return {
                "instance_id": instance_id,
                "instance_type": instance.get("InstanceType"),
                "region_code": region, "location": location_name,
                "operatingSystem": os_type,
                "tenancy": instance.get("Placement", {}).get("Tenancy", "Shared"),
            }
        
        elif service == "RDS":
            match = re.search(r":db:(?P<DBInstanceIdentifier>.*)", arn)
            if not match: return {}
            db_id = match.group("DBInstanceIdentifier")
            rds = session.client("rds")
            response = rds.describe_db_instances(DBInstanceIdentifier=db_id)
            instance = response["DBInstances"][0]

            return {
                "instance_id": db_id,
                "instance_type": instance.get("DBInstanceClass"),
                "engine": instance.get("Engine"),
                "region_code": region, "location": location_name,
            }
            
        return {}

    except ClientError as e:
        print(f"❌ AWS describe error for {arn}: {e.response['Error']['Message']}")
        return {}
    except Exception as e:
        print(f"❌ Unexpected error describing resource {arn}: {e}")
        return {}


def fetch_arns_grouped_by_user_id():
    """Fetches all infrastructure ARNs, grouped by user ID, skipping specific users."""
    session = SessionLocal()
    try:
        result = defaultdict(list)
        records = session.query(InfrastructureInventory.user_id, InfrastructureInventory.arn).all()
        for user_id, arn in records:
            if user_id in (5, 7):
                continue  # Skip user IDs 5 and 7
            print(f"Processing ARN for user {user_id}: {arn}")
            result[user_id].append(arn)
        return dict(result)
    finally:
        session.close()


# --- Main Logic ---

def collect_all_metrics(arns_by_user, config_path="app/core/cloudwatch_metrics_config.json"):
    """Collects CloudWatch metrics for all ARNs and stores them in the database."""
    config = json.load(open(config_path))
    db = SessionLocal()
    try:
        for user_id, arns in arns_by_user.items():
            for arn in arns:
                service, dim_values = None, None
                for s, details in config.items():
                    match = re.compile(details["ArnPattern"]).match(arn)
                    if match:
                        service, dim_values = s, match.groupdict()
                        break
                if not service: continue

                # --- Corrected Region Extraction Logic ---
                region_match = re.search(r"arn:aws:[^:]+:([^:]*):", arn)

                # Get the region from the ARN, or None if it's not found or is empty
                region_from_arn = region_match.group(1) if region_match else None

                # Default to 'us-east-1' if the extracted region is empty or None
                region = region_from_arn or "us-east-1"

                cw = boto3.client("cloudwatch", region_name=region)
                
                metric_result = {}
                for metric in config[service]["metrics"]:
                    try:
                        dimensions = [{"Name": k, "Value": dim_values[k]} for k in metric["Dimensions"]]
                        response = cw.get_metric_statistics(
                            Namespace=metric["Namespace"],
                            MetricName=metric["MetricName"],
                            Dimensions=dimensions,
                            StartTime=datetime.utcnow() - timedelta(days=14),
                            EndTime=datetime.utcnow(),
                            Period=metric["Period"],
                            Statistics=metric["Statistics"]
                        )
                        metric_result[metric["MetricName"]] = sorted(response.get("Datapoints", []), key=lambda x: x["Timestamp"])
                    except Exception as e:
                        print(f"⚠️ Could not fetch metric {metric['MetricName']} for {arn}: {e}")

                if metric_result:
                    additional_info = describe_aws_resource(user_id, arn, service, region)
                    create_or_update_metrics(db, user_id, arn, service, metric_result, additional_info)
        
        print("✅ Metrics collection and database update complete.")
    finally:
        db.close()




def generate_recommendations(rules_path="app/core/cloudwatch_recommendation_rules.json"):
    """Evaluates collected metrics against rules to generate recommendations."""
    db = SessionLocal()
    metrics_data = fetch_all_collected_metrics(db)
    rules = json.load(open(rules_path))
    db.close()

    sizing_maps = {
        "EC2": {"Downsize": INSTANCE_DOWNSIZE_MAP, "Upgrade": INSTANCE_UPSIZE_MAP},
        "RDS": {"Downsize": RDS_INSTANCE_DOWNSIZE_MAP, "Upgrade": RDS_INSTANCE_UPSIZE_MAP},
    }

    for record in metrics_data:
        resource_type = record.get("resource_type")
        if resource_type not in rules: continue

        userid = record["userid"]
        arn = record["arn"]
        metrics = record.get("metrics_data", {})
        additional_info = record.get("additional_info", {})
        
        current_instance_class = additional_info.get("instance_type")
        if not current_instance_class: continue

        current_hourly_price = get_resource_hourly_price(resource_type, additional_info)
        # ✅ FIX: Check for invalid pricing and skip this resource
        if current_hourly_price <= 0:
            print(f"⚠️ Skipping {arn} due to missing or invalid price info for {current_instance_class} (price: {current_hourly_price}).")
            continue

        for metric_name, datapoints in metrics.items():
            if metric_name not in rules[resource_type]: continue
            
            for rule in rules[resource_type][metric_name]:
                stat_type = rule["stat"]
                stat_values = [dp.get(stat_type) for dp in datapoints if dp.get(stat_type) is not None]
                if not stat_values: continue

                avg_stat_value = mean(stat_values)
                
                # ✅ FIX: Improved condition evaluation with better error handling
                try:
                    condition = rule["condition"]
                    # Handle percentage conditions
                    if condition.endswith("%"):
                        condition_value = float(condition[:-1])
                        comparison_value = avg_stat_value * 100  # Convert to percentage
                    else:
                        condition_value = float(re.search(r"(\d+\.?\d*)", condition).group(1))
                        comparison_value = avg_stat_value
                    
                    # Determine the operator
                    if ">=" in condition:
                        condition_met = comparison_value >= condition_value
                    elif "<=" in condition:
                        condition_met = comparison_value <= condition_value
                    elif ">" in condition:
                        condition_met = comparison_value > condition_value
                    elif "<" in condition:
                        condition_met = comparison_value < condition_value
                    elif "==" in condition:
                        condition_met = comparison_value == condition_value
                    else:
                        print(f"⚠️ Unknown condition operator in: {condition}")
                        continue
                        
                    if not condition_met:
                        continue
                        
                except (ValueError, AttributeError) as e:
                    print(f"⚠️ Error parsing condition '{rule['condition']}': {e}")
                    continue

                action = rule["recommendation"]
                suggested_instance = None
                llm_text = ""
                cost_impact = ""
                new_hourly_price = -1.0

                if action in ["Downsize", "Upgrade"]:
                    suggestion_map = sizing_maps.get(resource_type, {}).get(action, {})
                    suggested_instance = suggestion_map.get(current_instance_class)

                    if suggested_instance:
                        mock_info = additional_info.copy()
                        mock_info["instance_type"] = suggested_instance
                        new_hourly_price = get_resource_hourly_price(resource_type, mock_info)
                        
                        # ✅ FIX: Check for valid pricing before calculating savings
                        if new_hourly_price > 0:
                            current_annual = current_hourly_price * 24 * 365
                            new_annual = new_hourly_price * 24 * 365
                            delta = current_annual - new_annual
                            
                            # ✅ FIX: Additional check to prevent division by zero
                            if current_annual > 0:
                                delta_percent = abs((delta / current_annual) * 100)
                            else:
                                delta_percent = 0.0
                            
                            cost_impact = (f"Annual Cost Impact: {'Savings' if delta > 0 else 'Increase'} "
                                         f"of ${abs(delta):.2f} ({delta_percent:.1f}%)")

                            llm_text = generate_llm_recommendation(
                                resource_display_name=f"AWS {resource_type}",
                                instance_type=current_instance_class,
                                suggested_instance=suggested_instance,
                                cost_hourly=new_hourly_price,
                                cost_saving=abs(delta),
                                percent_saving=delta_percent
                            )
                        else:
                            cost_impact = f"Suggested instance '{suggested_instance}' pricing unavailable."
                            llm_text = f"A {action.lower()} is recommended from {current_instance_class} to {suggested_instance}, but pricing information is not available."
                    else:
                        cost_impact = "No direct sizing match found in maps."
                        llm_text = f"A {action.lower()} is recommended for {current_instance_class}, but no suitable alternative instance type was found in the configuration."
                else:
                    cost_impact = f"Action: {action}."
                    llm_text = f"A recommendation to '{action}' was triggered for the {metric_name} metric."

                # --- Assemble full recommendation for console output ---
                full_rec_console = (
                    f"Metric: {metric_name} ({stat_type}) was {round(avg_stat_value, 2)}, triggering rule ({rule['condition']}).\n"
                    f"Recommendation: {action}\n"
                    f"Current Instance: {current_instance_class} @ ${current_hourly_price:.4f}/hr\n"
                )
                if suggested_instance and new_hourly_price > 0:
                    full_rec_console += f"Suggested Instance: {suggested_instance} @ ${new_hourly_price:.4f}/hr\n"
                full_rec_console += f"{cost_impact}\n\n{llm_text}"

                print(f"\n✅ Generated Recommendation for [User {userid}] - {arn}")
                print(full_rec_console)
                
                # --- Assemble clean recommendation for database ---
                # --- Parse LLM response into Action, Impact, Savings ---
                parsed_action = parsed_impact = parsed_savings = None
                try:
                    pattern = r"Action:\s*(.+?)\n+Impact:\s*(.+?)\n+Savings:\s*(.+)"
                    match = re.search(pattern, llm_text, re.DOTALL | re.IGNORECASE)
                    if match:
                        parsed_action = {"text": match.group(1).strip()}
                        parsed_impact = {"text": match.group(2).strip()}
                        parsed_savings = {"text": match.group(3).strip()}
                    else:
                        print(f"⚠️ Could not parse LLM response for action/impact/savings. Storing entire text as recommendation only.")
                except Exception as e:
                    print(f"❌ Error parsing LLM text: {e}")

                # --- Assemble clean recommendation for database ---
                db_recommendation_text = f"Metric: {metric_name}\n\n{llm_text}"

                db_rec_session = SessionLocal()
                try:
                    insert_or_update(
                        db=db_rec_session,
                        userid=userid,
                        resource_type=resource_type,
                        arn=arn,
                        recommendation_text=db_recommendation_text,
                        action=parsed_action,
                        impact=parsed_impact,
                        savings=parsed_savings
                    )
                except Exception as e:
                    print(f"❌ Error inserting recommendation: {e}")
                finally:
                    db_rec_session.close()



# --- Execution ---
if __name__ == "__main__":
    print("--- Starting Cloud Cost Advisor ---")
    
    print("\n[Step 1/3] Fetching resource ARNs from database...")
    arns_by_user = fetch_arns_grouped_by_user_id()
    if not arns_by_user:
        print("No ARNs found. Exiting.")
    else:
        print(f"Found resources for {len(arns_by_user)} user(s).")

        print("\n[Step 2/3] Collecting CloudWatch metrics for all resources...")
        collect_all_metrics(arns_by_user)
        
        print("\n[Step 3/3] Generating recommendations based on collected data...")
        generate_recommendations()
        
    print("\n--- Advisor run complete. ---")