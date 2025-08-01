# # from app.database import SessionLocal
# # from app.models.infrastructure_inventory import InfrastructureInventory
# # from app.db.metrics_collector import create_or_update_metrics,fetch_all_collected_metrics
# # from app.database import SessionLocal

# # from app.db.recommendation import insert_or_update
# # # from openai import OpenAI
# # from statistics import mean
# # import os
# # from dotenv import load_dotenv

# # load_dotenv()
# # # openai.api_key = os.getenv("OPENAI_API_KEY")

# # from collections import defaultdict

# # from app.db.connection import get_user_connections_by_type
# # from app.core.existing_to_tf import get_aws_credentials_from_db
# # from botocore.exceptions import ClientError


# # import re
# # from datetime import datetime, timedelta
# # from pathlib import Path
# # import boto3
# # import json



# # REGION_NAME_MAP = {
# #     "us-east-1": "US East (N. Virginia)",
# #     "us-east-2": "US East (Ohio)",
# #     "us-west-1": "US West (N. California)",
# #     "us-west-2": "US West (Oregon)",
# #     "eu-west-1": "EU (Ireland)",
# #     "eu-central-1": "EU (Frankfurt)",
# #     "ap-south-1": "Asia Pacific (Mumbai)",
# #     "ap-northeast-1": "Asia Pacific (Tokyo)",
# #     "ap-southeast-1": "Asia Pacific (Singapore)",
# #     "sa-east-1": "South America (São Paulo)",
# #     # Add more if needed
# # }
# # INSTANCE_DOWNSIZE_MAP = {
# #     # T3 family
# #     "t3.2xlarge": "t3.xlarge",
# #     "t3.xlarge": "t3.large",
# #     "t3.large": "t3.medium",
# #     "t3.medium": "t3.small",
# #     "t3.small": "t3.micro",
# #     "t3.micro": "t3.nano",

# #     # T2 family
# #     "t2.2xlarge": "t2.xlarge",
# #     "t2.xlarge": "t2.large",
# #     "t2.large": "t2.medium",
# #     "t2.medium": "t2.small",
# #     "t2.small": "t2.micro",
# #     "t2.micro": "t3.nano",        # ✅ cross-family cheaper alternative
# #     "t2.nano": "t3.nano",         # ✅ cheaper ARM-based alternative

# #     # M5 family
# #     "m5.24xlarge": "m5.12xlarge",
# #     "m5.12xlarge": "m5.4xlarge",
# #     "m5.4xlarge": "m5.2xlarge",
# #     "m5.2xlarge": "m5.xlarge",
# #     "m5.xlarge": "m5.large",
# #     "m5.large": "t3.large",       # ✅ cost-effective general purpose

# #     # M4 family
# #     "m4.16xlarge": "m4.10xlarge",
# #     "m4.10xlarge": "m4.4xlarge",
# #     "m4.4xlarge": "m4.2xlarge",
# #     "m4.2xlarge": "m4.xlarge",
# #     "m4.xlarge": "m4.large",
# #     "m4.large": "t3.medium",      # ✅ modern alternative

# #     # C5 family
# #     "c5.24xlarge": "c5.12xlarge",
# #     "c5.12xlarge": "c5.4xlarge",
# #     "c5.4xlarge": "c5.2xlarge",
# #     "c5.2xlarge": "c5.xlarge",
# #     "c5.xlarge": "c5.large",
# #     "c5.large": "t3.medium",      # ✅ if CPU not fully utilized

# #     # T4g family (ARM)
# #     "t4g.large": "t4g.medium",
# #     "t4g.medium": "t4g.small",
# #     "t4g.small": "t4g.micro",
# #     "t4g.micro": "t4g.nano"
# # }


# # INSTANCE_UPSIZE_MAP = {
# #     # T3 family
# #     "t3.nano": "t3.micro",
# #     "t3.micro": "t3.small",
# #     "t3.small": "t3.medium",
# #     "t3.medium": "t3.large",
# #     "t3.large": "t3.xlarge",
# #     "t3.xlarge": "t3.2xlarge",

# #     # T2 family
# #     "t2.nano": "t2.micro",
# #     "t2.micro": "t2.small",
# #     "t2.small": "t2.medium",
# #     "t2.medium": "t2.large",
# #     "t2.large": "t2.xlarge",
# #     "t2.xlarge": "t2.2xlarge",

# #     # M5 family
# #     "m5.large": "m5.xlarge",
# #     "m5.xlarge": "m5.2xlarge",
# #     "m5.2xlarge": "m5.4xlarge",
# #     "m5.4xlarge": "m5.12xlarge",
# #     "m5.12xlarge": "m5.24xlarge",

# #     # C5 family
# #     "c5.large": "c5.xlarge",
# #     "c5.xlarge": "c5.2xlarge",
# #     "c5.2xlarge": "c5.4xlarge",
# #     "c5.4xlarge": "c5.12xlarge",
# #     "c5.12xlarge": "c5.24xlarge",

# #     # T4g family
# #     "t4g.nano": "t4g.micro",
# #     "t4g.micro": "t4g.small",
# #     "t4g.small": "t4g.medium",
# #     "t4g.medium": "t4g.large",

# #     # Extra cross-family upsize
# #     "t3.nano": "t4g.micro",        
# #     "t2.nano": "t3.micro",         
# #     "t2.micro": "t3.small",
# # }






# # from openai import OpenAI

# # api_key = os.getenv("OPENAI_API_KEY")
# # openai_client = OpenAI(api_key=api_key)

# # def generate_llm_recommendation(instance_type, suggested_instance, cost_hourly, cost_saving, percent_saving):
# #     prompt = f"""
# # You are a cloud cost optimization advisor.

# # The current AWS EC2 instance is:
# # - Type: {instance_type}

# # Suggested new instance type:
# # - {suggested_instance}
# # - New hourly cost: ${cost_hourly:.4f}
# # - Annual cost savings: ${cost_saving:.2f} ({percent_saving:.1f}%)

# # Generate a recommendation divided into:
# # 1. Action: What change to make
# # 2. Impact: Why this helps
# # 3. Savings: The cost benefit

# # Be concise and clear.
# # Do not include any emojis and all.
# # """

# #     try:
# #         response = openai_client.chat.completions.create(
# #             model="gpt-4",
# #             messages=[
# #                 {"role": "system", "content": "You're a cloud cost optimization advisor."},
# #                 {"role": "user", "content": prompt}
# #             ],
# #             max_tokens=5000,
# #             temperature=0.5
# #         )
# #         return response.choices[0].message.content.strip()

# #     except Exception as e:
# #         print(f"❌ LLM Error: {e}")
# #         return f"⚠️ Unable to generate LLM recommendation: {e}"





# # def get_location_from_region(region_code: str, pricing_client=None) -> str:
# #     """
# #     Maps AWS region codes to human-readable location names.
# #     Optionally uses pricing_client for dynamic lookup (not required here).
# #     """
# #     return REGION_NAME_MAP.get(region_code, "US East (N. Virginia)")




# # def get_instance_hourly_price(instance_info: dict) -> float:
# #     """
# #     Takes additional_info dict from describe_aws_resource() and returns the hourly price of the instance.

# #     Args:
# #         instance_info (dict): Output from describe_aws_resource

# #     Returns:
# #         float: Hourly price in USD, or -1.0 if not found or invalid
# #     """
# #     try:
# #         # Required fields from instance_info
# #         instance_type = instance_info.get("instance_type")
# #         location = instance_info.get("location", "US East (N. Virginia)")
# #         operating_system = instance_info.get("operatingSystem", "Linux")
# #         pre_installed = instance_info.get("preInstalledSw", "NA")
# #         tenancy = instance_info.get("tenancy", "default")
# #         capacity_status = instance_info.get("capacitystatus", "Used")

# #         if not instance_type or not location:
# #             print("❌ Missing instance_type or location for pricing.")
# #             return -1.0

# #         if tenancy == "default":
# #             tenancy = "Shared"

# #         # Show query input to debug failures
# #         print("\n🔎 Pricing Query Params:")
# #         print(f"  Instance Type: {instance_type}")
# #         print(f"  Location: {location}")
# #         print(f"  OS: {operating_system}")
# #         print(f"  Preinstalled SW: {pre_installed}")
# #         print(f"  Tenancy: {tenancy}")
# #         print(f"  Capacity Status: {capacity_status}")

# #         client = boto3.client("pricing", region_name="us-east-1")

# #         filters = [
# #             {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
# #             {"Type": "TERM_MATCH", "Field": "location", "Value": location},
# #             {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": operating_system},
# #             {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": pre_installed},
# #             {"Type": "TERM_MATCH", "Field": "tenancy", "Value": tenancy},
# #             {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": capacity_status}
# #         ]

# #         # Initial pricing call
# #         response = client.get_products(
# #             ServiceCode="AmazonEC2",
# #             Filters=filters,
# #             MaxResults=1
# #         )

# #         # If empty, try fallback (without capacitystatus)
# #         if not response["PriceList"]:
# #             print("⚠️ No pricing data with capacitystatus, retrying without it...")
# #             fallback_filters = [f for f in filters if f["Field"] != "capacitystatus"]
# #             response = client.get_products(
# #                 ServiceCode="AmazonEC2",
# #                 Filters=fallback_filters,
# #                 MaxResults=1
# #             )

# #         if not response["PriceList"]:
# #             print(f"❌ Still no pricing found for {instance_type} in {location}")
# #             return -1.0

# #         price_item = json.loads(response["PriceList"][0])
# #         terms = price_item.get("terms", {}).get("OnDemand", {})
# #         for term_id, term in terms.items():
# #             price_dimensions = term.get("priceDimensions", {})
# #             for dim_id, dim in price_dimensions.items():
# #                 price = float(dim["pricePerUnit"]["USD"])
# #                 return price

# #         print(f"⚠️ Pricing info not found in 'terms' block.")
# #         return -1.0

# #     except Exception as e:
# #         print(f"❌ Failed to fetch pricing for instance: {e}")
# #         return -1.0



# # def describe_aws_resource(user_id: int, arn: str, service: str, region: str) -> dict:
# #     from app.core.existing_to_tf import get_aws_credentials_from_db
# #     from botocore.exceptions import ClientError

# #     db = SessionLocal()

# #     # ✅ Get credentials safely
# #     access_key, secret_key = get_aws_credentials_from_db(user_id)
# #     db.close()

# #     if not access_key or not secret_key:
# #         print(f"⚠️ Missing AWS credentials for user {user_id}")
# #         return {}

# #     try:
# #         session = boto3.Session(
# #             aws_access_key_id=access_key,
# #             aws_secret_access_key=secret_key,
# #             region_name=region
# #         )

# #         if service == "EC2":
# #             match = re.search(r"instance/(i-[a-zA-Z0-9]+)", arn)
# #             if not match:
# #                 print(f"⚠️ Could not extract instance ID from ARN: {arn}")
# #                 return {}

# #             instance_id = match.group(1)
# #             ec2 = session.client("ec2")

# #             try:
# #                 response = ec2.describe_instances(InstanceIds=[instance_id])
# #                 reservations = response.get("Reservations", [])
# #                 if not reservations or not reservations[0].get("Instances"):
# #                     print(f"⚠️ Instance not found or unavailable for ARN: {arn}")
# #                     return {}

# #                 instance = reservations[0]["Instances"][0]

# #             except ClientError as e:
# #                 print(f"❌ AWS describe error for {arn}: {e}")
# #                 return {}

# #             instance_type = instance.get("InstanceType")
# #             tenancy = instance.get("Placement", {}).get("Tenancy", "default")
# #             launch_time = str(instance.get("LaunchTime"))
# #             platform_details = instance.get("PlatformDetails", "Linux/UNIX")
# #             operating_system = "Linux"
# #             if "Windows" in platform_details:
# #                 operating_system = "Windows"

# #             pricing = session.client("pricing", region_name="us-east-1")
# #             location_name = get_location_from_region(region, pricing)

# #             return {
# #                 "instance_id": instance_id,
# #                 "instance_type": instance_type,
# #                 "availability_zone": instance.get("Placement", {}).get("AvailabilityZone"),
# #                 "launch_time": launch_time,
# #                 "region_code": region,
# #                 "location": location_name,
# #                 "tenancy": tenancy,
# #                 "operatingSystem": operating_system,
# #                 "preInstalledSw": "NA",
# #                 "capacitystatus": "Used"
# #             }

# #         # Other AWS services can be handled similarly here
# #         return {}

# #     except Exception as e:
# #         print(f"❌ Unexpected error during AWS resource description: {e}")
# #         return {}




# # def fetch_arns_grouped_by_user_id():
# #     session = SessionLocal()
# #     try:
# #         result = defaultdict(list)
# #         records = session.query(InfrastructureInventory.user_id, InfrastructureInventory.arn).all()
# #         for user_id, arn in records:
# #             result[user_id].append(arn)
# #         return dict(result)
# #     finally:
# #         session.close()



# # def load_metric_config(config_path="cloudwatch_metrics_config.json"):
# #     with open(config_path, "r") as f:
# #         return json.load(f)

# # def get_cloudwatch_client(region="us-east-1"):
# #     return boto3.client("cloudwatch", region_name=region)

# # def extract_service_and_dimensions(arn, config):
# #     for service, details in config.items():
# #         pattern = re.compile(details["ArnPattern"])
# #         match = pattern.match(arn)
# #         if match:
# #             return service, match.groupdict()
# #     return None, None

# # def fetch_metrics_for_arn(cw, namespace, metric_name, dimensions, statistics, period, days=14):
# #     now = datetime.utcnow()
# #     start_time = now - timedelta(days=days)

# #     response = cw.get_metric_statistics(
# #         Namespace=namespace,
# #         MetricName=metric_name,
# #         Dimensions=[{"Name": k, "Value": v} for k, v in dimensions.items()],
# #         StartTime=start_time,
# #         EndTime=now,
# #         Period=period,
# #         Statistics=statistics
# #     )
# #     datapoints = response.get("Datapoints", [])
# #     return sorted(datapoints, key=lambda x: x["Timestamp"])


# # def collect_all_metrics(arns_by_user, config_path="app\\core\\cloudwatch_metrics_config.json", output_path="cloudwatch_metrics_output.json"):
# #     config = load_metric_config(config_path)
# #     results = {}
# #     db = SessionLocal()

# #     try:
# #         for user_id, arns in arns_by_user.items():
# #             results[user_id] = {}
# #             for arn in arns:
# #                 service, dim_values = extract_service_and_dimensions(arn, config)
# #                 if not service:
# #                     continue  # Skip unknown services

# #                 service_conf = config[service]
# #                 results[user_id][arn] = {}
# #                 region_match = re.search(r"arn:aws:[^:]+:([^:]*):", arn)
# #                 region = region_match.group(1) if region_match and region_match.group(1) else "us-east-1"
# #                 cw = get_cloudwatch_client(region)

# #                 metric_result = {}
# #                 for metric in service_conf["metrics"]:
# #                     dim_keys = metric["Dimensions"]
# #                     try:
# #                         dimensions = {key: dim_values[key] for key in dim_keys}
# #                     except KeyError:
# #                         continue  # Missing required dimension keys

# #                     datapoints = fetch_metrics_for_arn(
# #                         cw,
# #                         metric["Namespace"],
# #                         metric["MetricName"],
# #                         dimensions,
# #                         metric["Statistics"],
# #                         metric["Period"],
# #                         days=14
# #                     )

# #                     metric_result[metric["MetricName"]] = datapoints
# #                     results[user_id][arn][metric["MetricName"]] = datapoints

# #                 # 🔄 Insert into DB
# #                 if metric_result:
# #                     # 🔍 Fetch additional info from AWS
# #                     additional_info = describe_aws_resource(
# #                         user_id=user_id,
# #                         arn=arn,
# #                         service=service,
# #                         region=region
# #                     )
# #                     if additional_info and service == "EC2":
# #                         hourly_price = get_instance_hourly_price(additional_info)
# #                         instance_type = additional_info.get("instance_type", "unknown")
# #                         print(f"💲 Instance Type: {instance_type}, Hourly Price: ${hourly_price:.4f}")
# #                     # 🔄 Insert with extra info
# #                     create_or_update_metrics(
# #                         db=db,
# #                         userid=user_id,
# #                         arn=arn,
# #                         resource_type=service,
# #                         metrics_data=metric_result,
# #                         additional_info=additional_info
# #                     )


# #         # Save to file (optional reporting/logging)
# #         with open(output_path, "w") as f:
# #             json.dump(results, f, indent=2, default=str)

# #         print(f"✅ Metrics saved to DB and JSON: {output_path}")
# #         return results

# #     finally:
# #         db.close()


# # from statistics import mean

# # def load_recommendation_rules(path="app\core\cloudwatch_recommendation_rules.json"):
# #     with open(path, "r") as f:
# #         return json.load(f)

# # def evaluate_condition(stat_value, condition_str):
# #     try:
# #         if condition_str.endswith("%"):
# #             condition_str = condition_str.replace("%", "")
# #             stat_value *= 100  # Normalize to percentage
# #         if ">=" in condition_str:
# #             return stat_value >= float(condition_str.split(">=")[-1])
# #         elif "<=" in condition_str:
# #             return stat_value <= float(condition_str.split("<=")[-1])
# #         elif ">" in condition_str:
# #             return stat_value > float(condition_str.split(">")[-1])
# #         elif "<" in condition_str:
# #             return stat_value < float(condition_str.split("<")[-1])
# #         elif "==" in condition_str:
# #             return stat_value == float(condition_str.split("==")[-1])
# #         return False
# #     except Exception as e:
# #         print(f"❌ Error evaluating condition: {condition_str} on value {stat_value}: {e}")
# #         return False

# # def generate_recommendations():
# #     db = SessionLocal()
# #     metrics_data = fetch_all_collected_metrics(db)
# #     db.close()

# #     rules = load_recommendation_rules()
# #     recommendations = []

# #     for record in metrics_data:
# #         resource_type = record["resource_type"]
# #         metrics = record["metrics_data"]
# #         userid = record["userid"]
# #         arn = record["arn"]

# #         if resource_type != "EC2":
# #             continue

# #         additional_info = describe_aws_resource(userid, arn, "EC2", record.get("metrics_data", {}).get("region_code", "us-east-1"))
# #         if not additional_info:
# #             continue

# #         current_instance = additional_info.get("instance_type")
# #         current_hourly_price = get_instance_hourly_price(additional_info)
# #         if current_hourly_price == -1:
# #             continue

# #         for metric_name, datapoints in metrics.items():
# #             if metric_name not in rules.get(resource_type, {}):
# #                 continue

# #             for rule in rules[resource_type][metric_name]:
# #                 stat_type = rule["stat"]
# #                 stat_values = [dp.get(stat_type) for dp in datapoints if dp.get(stat_type) is not None]

# #                 if not stat_values:
# #                     continue

# #                 avg_stat_value = mean(stat_values)
# #                 if evaluate_condition(avg_stat_value, rule["condition"]):
# #                     action = rule["recommendation"]
# #                     suggested_instance = None

# #                     if action == "Downsize":
# #                         suggested_instance = INSTANCE_DOWNSIZE_MAP.get(current_instance)
# #                     elif action == "Upgrade":
# #                         suggested_instance = INSTANCE_UPSIZE_MAP.get(current_instance)

# #                     if suggested_instance:
# #                         # Create mock additional_info to price suggestion
# #                         mock_info = additional_info.copy()
# #                         mock_info["instance_type"] = suggested_instance
# #                         new_hourly_price = get_instance_hourly_price(mock_info)

# #                         if new_hourly_price > 0:
# #                             current_annual = current_hourly_price * 24 * 365
# #                             new_annual = new_hourly_price * 24 * 365
# #                             delta = current_annual - new_annual
# #                             delta_percent = abs((delta / current_annual) * 100)

# #                             cost_impact = (
# #                                 f"💰 Annual Cost Impact: "
# #                                 f"{'Savings' if delta > 0 else 'Increase'} of ${abs(delta):.2f} ({delta_percent:.1f}%)"
# #                             )

# #                             # 🔗 LLM call
# #                             llm_text = generate_llm_recommendation(
# #                                 instance_type=current_instance,
# #                                 suggested_instance=suggested_instance,
# #                                 cost_hourly=new_hourly_price,
# #                                 cost_saving=abs(delta),
# #                                 percent_saving=delta_percent
# #                             )
# #                         else:
# #                             suggested_instance = None
# #                             cost_impact = "⚠️ Suggested instance pricing unavailable."
# #                             llm_text = f"{action} recommended for instance {current_instance}, but price lookup failed."
# #                     else:
# #                         cost_impact = "ℹ️ No matching size recommendation found."
# #                         llm_text = f"{action} is recommended but no alternative instance type found."

# #                     full_recommendation = (
# #                         f"Metric: {metric_name} ({stat_type}) = {round(avg_stat_value, 2)}\n"
# #                         f"Recommendation: {action}\n"
# #                         f"Current Instance: {current_instance} @ ${current_hourly_price:.4f}/hr\n"
# #                     )

# #                     if suggested_instance:
# #                         full_recommendation += (
# #                             f"Suggested Instance: {suggested_instance} @ ${new_hourly_price:.4f}/hr\n"
# #                             f"{cost_impact}\n\n{llm_text}"
# #                         )
# #                     else:
# #                         full_recommendation += f"{cost_impact}"

# #                     # DB Save
# #                     db_rec = SessionLocal()
# #                     insert_or_update(
# #                         db=db_rec,
# #                         userid=userid,
# #                         resource_type=resource_type,
# #                         arn=arn,
# #                         recommendation_text=full_recommendation
# #                     )
# #                     db_rec.close()

# #                     # Console output
# #                     print(f"\n🔍 [User {userid}] Resource: {arn}")
# #                     print(full_recommendation)

# #                     recommendations.append({
# #                         "userid": userid,
# #                         "arn": arn,
# #                         "resource_type": resource_type,
# #                         "metric": metric_name,
# #                         "stat_type": stat_type,
# #                         "average_value": round(avg_stat_value, 2),
# #                         "recommendation": full_recommendation
# #                     })

# #     return recommendations



# # # Example usage
# # if __name__ == "__main__":
# #     arns_by_user = fetch_arns_grouped_by_user_id()
# #     collect_all_metrics(arns_by_user)
# #     generate_recommendations()


# import os
# import re
# import json
# from datetime import datetime, timedelta
# from collections import defaultdict
# from statistics import mean

# import boto3
# from botocore.exceptions import ClientError
# from dotenv import load_dotenv
# from openai import OpenAI

# # --- Database Imports (assuming they are correctly set up) ---
# from app.database import SessionLocal
# from app.models.infrastructure_inventory import InfrastructureInventory
# from app.db.metrics_collector import create_or_update_metrics, fetch_all_collected_metrics
# from app.db.recommendation import insert_or_update
# from app.core.existing_to_tf import get_aws_credentials_from_db

# # --- Load Environment Variables ---
# load_dotenv()
# openai_api_key = os.getenv("OPENAI_API_KEY")
# if openai_api_key:
#     openai_client = OpenAI(api_key=openai_api_key)
# else:
#     print("⚠️ OpenAI API key not found. LLM recommendations will be disabled.")
#     openai_client = None

# # --- Configuration & Mappings ---

# REGION_NAME_MAP = {
#     "us-east-1": "US East (N. Virginia)",
#     "us-east-2": "US East (Ohio)",
#     "us-west-1": "US West (N. California)",
#     "us-west-2": "US West (Oregon)",
#     "eu-west-1": "EU (Ireland)",
#     "eu-central-1": "EU (Frankfurt)",
#     "ap-south-1": "Asia Pacific (Mumbai)",
#     "ap-northeast-1": "Asia Pacific (Tokyo)",
#     "ap-southeast-1": "Asia Pacific (Singapore)",
#     "sa-east-1": "South America (São Paulo)",
# }

# # --- EC2 Instance Sizing Maps ---
# INSTANCE_DOWNSIZE_MAP = {
#     # T3 family
#     "t3.2xlarge": "t3.xlarge", "t3.xlarge": "t3.large", "t3.large": "t3.medium",
#     "t3.medium": "t3.small", "t3.small": "t3.micro", "t3.micro": "t3.nano",
#     # T2 family
#     "t2.2xlarge": "t2.xlarge", "t2.xlarge": "t2.large", "t2.large": "t2.medium",
#     "t2.medium": "t2.small", "t2.small": "t2.micro", "t2.micro": "t3.nano",
#     # M5 family
#     "m5.24xlarge": "m5.12xlarge", "m5.12xlarge": "m5.4xlarge", "m5.4xlarge": "m5.2xlarge",
#     "m5.2xlarge": "m5.xlarge", "m5.xlarge": "m5.large", "m5.large": "t3.large",
# }

# INSTANCE_UPSIZE_MAP = {
#     # T3 family
#     "t3.nano": "t3.micro", "t3.micro": "t3.small", "t3.small": "t3.medium",
#     "t3.medium": "t3.large", "t3.large": "t3.xlarge", "t3.xlarge": "t3.2xlarge",
#     # T2 family
#     "t2.nano": "t2.micro", "t2.micro": "t2.small", "t2.small": "t2.medium",
#     "t2.medium": "t2.large", "t2.large": "t2.xlarge", "t2.xlarge": "t2.2xlarge",
#     # M5 family
#     "m5.large": "m5.xlarge", "m5.xlarge": "m5.2xlarge", "m5.2xlarge": "m5.4xlarge",
#     "m5.4xlarge": "m5.12xlarge", "m5.12xlarge": "m5.24xlarge",
# }

# # --- RDS Instance Sizing Maps (New) ---
# RDS_INSTANCE_DOWNSIZE_MAP = {
#     # T3 DB Instances
#     "db.t3.2xlarge": "db.t3.xlarge", "db.t3.xlarge": "db.t3.large",
#     "db.t3.large": "db.t3.medium", "db.t3.medium": "db.t3.small", "db.t3.small": "db.t3.micro",
#     # M5 DB Instances
#     "db.m5.24xlarge": "db.m5.12xlarge", "db.m5.12xlarge": "db.m5.8xlarge",
#     "db.m5.8xlarge": "db.m5.4xlarge", "db.m5.4xlarge": "db.m5.2xlarge",
#     "db.m5.2xlarge": "db.m5.xlarge", "db.m5.xlarge": "db.m5.large",
# }

# RDS_INSTANCE_UPSIZE_MAP = {
#     # T3 DB Instances
#     "db.t3.micro": "db.t3.small", "db.t3.small": "db.t3.medium", "db.t3.medium": "db.t3.large",
#     "db.t3.large": "db.t3.xlarge", "db.t3.xlarge": "db.t3.2xlarge",
#     # M5 DB Instances
#     "db.m5.large": "db.m5.xlarge", "db.m5.xlarge": "db.m5.2xlarge",
#     "db.m5.2xlarge": "db.m5.4xlarge", "db.m5.4xlarge": "db.m5.8xlarge",
#     "db.m5.8xlarge": "db.m5.12xlarge", "db.m5.12xlarge": "db.m5.24xlarge",
# }

# # --- Core Functions ---

# def generate_llm_recommendation(resource_display_name, instance_type, suggested_instance, cost_hourly, cost_saving, percent_saving):
#     """Generates a concise recommendation using an LLM."""
#     if not openai_client:
#         return "⚠️ LLM client not initialized. Cannot generate recommendation."

#     prompt = f"""
# You are a cloud cost optimization advisor.
# The current resource is a {resource_display_name}:
# - Type: {instance_type}

# A cost-saving change is recommended:
# - Suggested New Type: {suggested_instance}
# - New Hourly Cost: ${cost_hourly:.4f}
# - Estimated Annual Savings: ${cost_saving:.2f} ({percent_saving:.1f}%)

# Generate a brief recommendation with these sections:
# 1. Action: The specific change to make.
# 2. Impact: Why this change is beneficial.
# 3. Savings: The financial benefit.

# Be concise and clear. Do not use emojis or markdown formatting.
# """
#     try:
#         response = openai_client.chat.completions.create(
#             model="gpt-4",
#             messages=[
#                 {"role": "system", "content": "You are a cloud cost optimization advisor."},
#                 {"role": "user", "content": prompt}
#             ],
#             max_tokens=200,
#             temperature=0.5
#         )
#         return response.choices[0].message.content.strip()
#     except Exception as e:
#         print(f"❌ LLM Error: {e}")
#         return f"⚠️ Unable to generate LLM recommendation: {e}"

# def get_location_from_region(region_code: str) -> str:
#     """Maps an AWS region code to a human-readable location name."""
#     return REGION_NAME_MAP.get(region_code, "US East (N. Virginia)")

# def get_resource_hourly_price(service: str, resource_info: dict) -> float:
#     """Fetches the on-demand hourly price for an AWS resource with multiple fallbacks."""
#     try:
#         pricing_client = boto3.client("pricing", region_name="us-east-1")
#         location = resource_info.get("location", "US East (N. Virginia)")
#         instance_type = resource_info.get("instance_type")

#         if not all([service, instance_type, location]):
#             print("❌ Missing service, instance_type, or location for pricing.")
#             return -1.0

#         base_filters = [
#             {"Type": "TERM_MATCH", "Field": "location", "Value": location},
#             {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
#         ]
        
#         service_code = ""
#         initial_filters = []
#         if service == "EC2":
#             service_code = "AmazonEC2"
#             initial_filters = base_filters + [
#                 {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": resource_info.get("operatingSystem", "Linux")},
#                 {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
#                 {"Type": "TERM_MATCH", "Field": "tenancy", "Value": resource_info.get("tenancy", "Shared")},
#                 {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"}
#             ]
#         elif service == "RDS":
#             service_code = "AmazonRDS"
#             engine_map = {"postgres": "PostgreSQL", "mysql": "MySQL"}
#             db_engine = engine_map.get(resource_info.get("engine"), "MySQL")
            
#             initial_filters = base_filters + [
#                 {"Type": "TERM_MATCH", "Field": "databaseEngine", "Value": db_engine},
#                 {"Type": "TERM_MATCH", "Field": "deploymentOption", "Value": "Single-AZ"}
#             ]
#         else:
#             print(f"⚠️ Pricing not implemented for service: {service}")
#             return -1.0

#         response = pricing_client.get_products(ServiceCode=service_code, Filters=initial_filters, MaxResults=1)

#         # Fallback 1: For EC2, remove 'capacitystatus'
#         if not response.get("PriceList") and service == "EC2":
#             print(f"⚠️ No pricing data with 'capacitystatus' for {instance_type}. Retrying without it...")
#             fallback_filters_1 = [f for f in initial_filters if f["Field"] != "capacitystatus"]
#             response = pricing_client.get_products(ServiceCode=service_code, Filters=fallback_filters_1, MaxResults=1)

#         # Fallback 2: For EC2, also remove 'preInstalledSw'
#         if not response.get("PriceList") and service == "EC2":
#             print(f"⚠️ Still no pricing data. Retrying without 'preInstalledSw' as well...")
#             fallback_filters_2 = [f for f in initial_filters if f["Field"] not in ["capacitystatus", "preInstalledSw"]]
#             response = pricing_client.get_products(ServiceCode=service_code, Filters=fallback_filters_2, MaxResults=1)
            
#         # Fallback 3: For EC2, use only the most basic filters as a last resort
#         if not response.get("PriceList") and service == "EC2":
#             print(f"⚠️ Last resort. Retrying with only location and instance type for {instance_type}...")
#             response = pricing_client.get_products(ServiceCode=service_code, Filters=base_filters, MaxResults=1)

#         if not response.get("PriceList"):
#             print(f"❌ All fallbacks failed. No pricing data found for {instance_type} in {location}.")
#             return -1.0

#         price_item = json.loads(response["PriceList"][0])
#         terms = price_item.get("terms", {}).get("OnDemand", {})
#         for term in terms.values():
#             for dim in term.get("priceDimensions", {}).values():
#                 return float(dim["pricePerUnit"]["USD"])

#         print(f"⚠️ Price dimensions not found for {instance_type}.")
#         return -1.0

#     except Exception as e:
#         print(f"❌ Failed to fetch pricing for {resource_info.get('instance_type')}: {e}")
#         return -1.0

# def describe_aws_resource(user_id: int, arn: str, service: str, region: str) -> dict:
#     """
#     Describes an AWS resource (EC2 or RDS) and returns its key attributes.
#     """
#     access_key, secret_key = get_aws_credentials_from_db(user_id)
#     if not access_key or not secret_key:
#         print(f"⚠️ Missing AWS credentials for user {user_id}")
#         return {}

#     try:
#         session = boto3.Session(aws_access_key_id=access_key, aws_secret_access_key=secret_key, region_name=region)
#         location_name = get_location_from_region(region)

#         if service == "EC2":
#             match = re.search(r"instance/(i-[a-zA-Z0-9]+)", arn)
#             if not match: return {}
#             instance_id = match.group(1)
#             ec2 = session.client("ec2")
#             response = ec2.describe_instances(InstanceIds=[instance_id])
#             instance = response["Reservations"][0]["Instances"][0]
            
#             platform = instance.get("PlatformDetails", "Linux/UNIX")
#             os_type = "Windows" if "Windows" in platform else "Linux"

#             return {
#                 "instance_id": instance_id,
#                 "instance_type": instance.get("InstanceType"),
#                 "region_code": region, "location": location_name,
#                 "operatingSystem": os_type,
#                 "tenancy": instance.get("Placement", {}).get("Tenancy", "Shared"),
#             }
        
#         elif service == "RDS":
#             match = re.search(r":db:(?P<DBInstanceIdentifier>.*)", arn)
#             if not match: return {}
#             db_id = match.group("DBInstanceIdentifier")
#             rds = session.client("rds")
#             response = rds.describe_db_instances(DBInstanceIdentifier=db_id)
#             instance = response["DBInstances"][0]

#             return {
#                 "instance_id": db_id,
#                 "instance_type": instance.get("DBInstanceClass"),
#                 "engine": instance.get("Engine"),
#                 "region_code": region, "location": location_name,
#             }
            
#         return {}

#     except ClientError as e:
#         print(f"❌ AWS describe error for {arn}: {e.response['Error']['Message']}")
#         return {}
#     except Exception as e:
#         print(f"❌ Unexpected error describing resource {arn}: {e}")
#         return {}


# def fetch_arns_grouped_by_user_id():
#     """Fetches all infrastructure ARNs, grouped by user ID, skipping specific users."""
#     session = SessionLocal()
#     try:
#         result = defaultdict(list)
#         records = session.query(InfrastructureInventory.user_id, InfrastructureInventory.arn).all()
#         for user_id, arn in records:
#             if user_id in (5, 7):
#                 continue  # Skip user IDs 5 and 7
#             print(f"Processing ARN for user {user_id}: {arn}")
#             result[user_id].append(arn)
#         return dict(result)
#     finally:
#         session.close()


# # --- Main Logic ---

# def collect_all_metrics(arns_by_user, config_path="app/core/cloudwatch_metrics_config.json"):
#     """Collects CloudWatch metrics for all ARNs and stores them in the database."""
#     config = json.load(open(config_path))
#     db = SessionLocal()
#     try:
#         for user_id, arns in arns_by_user.items():
#             for arn in arns:
#                 service, dim_values = None, None
#                 for s, details in config.items():
#                     match = re.compile(details["ArnPattern"]).match(arn)
#                     if match:
#                         service, dim_values = s, match.groupdict()
#                         break
#                 if not service: continue

#                 # --- Corrected Region Extraction Logic ---
#                 region_match = re.search(r"arn:aws:[^:]+:([^:]*):", arn)

#                 # Get the region from the ARN, or None if it's not found or is empty
#                 region_from_arn = region_match.group(1) if region_match else None

#                 # Default to 'us-east-1' if the extracted region is empty or None
#                 region = region_from_arn or "us-east-1"

#                 cw = boto3.client("cloudwatch", region_name=region)
                
#                 metric_result = {}
#                 for metric in config[service]["metrics"]:
#                     try:
#                         dimensions = [{"Name": k, "Value": dim_values[k]} for k in metric["Dimensions"]]
#                         response = cw.get_metric_statistics(
#                             Namespace=metric["Namespace"],
#                             MetricName=metric["MetricName"],
#                             Dimensions=dimensions,
#                             StartTime=datetime.utcnow() - timedelta(days=14),
#                             EndTime=datetime.utcnow(),
#                             Period=metric["Period"],
#                             Statistics=metric["Statistics"]
#                         )
#                         metric_result[metric["MetricName"]] = sorted(response.get("Datapoints", []), key=lambda x: x["Timestamp"])
#                     except Exception as e:
#                         print(f"⚠️ Could not fetch metric {metric['MetricName']} for {arn}: {e}")

#                 if metric_result:
#                     additional_info = describe_aws_resource(user_id, arn, service, region)
#                     create_or_update_metrics(db, user_id, arn, service, metric_result, additional_info)
        
#         print("✅ Metrics collection and database update complete.")
#     finally:
#         db.close()


# def generate_recommendations(rules_path="app\core\cloudwatch_recommendation_rules.json"):
#     """Evaluates collected metrics against rules to generate recommendations."""
#     db = SessionLocal()
#     metrics_data = fetch_all_collected_metrics(db)
#     rules = json.load(open(rules_path))
#     db.close()

#     sizing_maps = {
#         "EC2": {"Downsize": INSTANCE_DOWNSIZE_MAP, "Upgrade": INSTANCE_UPSIZE_MAP},
#         "RDS": {"Downsize": RDS_INSTANCE_DOWNSIZE_MAP, "Upgrade": RDS_INSTANCE_UPSIZE_MAP},
#     }

#     for record in metrics_data:
#         resource_type = record.get("resource_type")
#         if resource_type not in rules: continue

#         userid = record["userid"]
#         arn = record["arn"]
#         metrics = record.get("metrics_data", {})
#         additional_info = record.get("additional_info", {})
        
#         current_instance_class = additional_info.get("instance_type")
#         if not current_instance_class: continue

#         current_hourly_price = get_resource_hourly_price(resource_type, additional_info)
#         if current_hourly_price == -1.0:
#             print(f"⚠️ Skipping {arn} due to missing price info for {current_instance_class}.")
#             continue

#         for metric_name, datapoints in metrics.items():
#             if metric_name not in rules[resource_type]: continue
            
#             for rule in rules[resource_type][metric_name]:
#                 stat_type = rule["stat"]
#                 stat_values = [dp.get(stat_type) for dp in datapoints if dp.get(stat_type) is not None]
#                 if not stat_values: continue

#                 avg_stat_value = mean(stat_values)
#                 match = re.match(r"([<>=]+)\s*(\d+\.?\d*)", rule["condition"])
#                 if not match or not eval(f"{avg_stat_value} {match.group(1)} {match.group(2)}"):
#                     continue

#                 action = rule["recommendation"]
#                 suggested_instance = None
#                 llm_text = ""
#                 cost_impact = ""
#                 new_hourly_price = -1.0

#                 if action in ["Downsize", "Upgrade"]:
#                     suggestion_map = sizing_maps.get(resource_type, {}).get(action, {})
#                     suggested_instance = suggestion_map.get(current_instance_class)

#                     if suggested_instance:
#                         mock_info = additional_info.copy()
#                         mock_info["instance_type"] = suggested_instance
#                         new_hourly_price = get_resource_hourly_price(resource_type, mock_info)
                        
#                         if new_hourly_price > 0:
#                             delta = (current_hourly_price - new_hourly_price) * 24 * 365
#                             delta_percent = abs((delta / (current_hourly_price * 24 * 365)) * 100)
                            
#                             cost_impact = (f"Annual Cost Impact: {'Savings' if delta > 0 else 'Increase'} "
#                                          f"of ${abs(delta):.2f} ({delta_percent:.1f}%)")

#                             llm_text = generate_llm_recommendation(
#                                 resource_display_name=f"AWS {resource_type}",
#                                 instance_type=current_instance_class,
#                                 suggested_instance=suggested_instance,
#                                 cost_hourly=new_hourly_price,
#                                 cost_saving=abs(delta),
#                                 percent_saving=delta_percent
#                             )
#                         else:
#                             cost_impact = f"Suggested instance '{suggested_instance}' pricing unavailable."
#                     else:
#                         cost_impact = "No direct sizing match found in maps."
#                 else:
#                     cost_impact = f"Action: {action}."
#                     llm_text = f"A recommendation to '{action}' was triggered for the {metric_name} metric."

#                 # --- Assemble full recommendation for console output ---
#                 full_rec_console = (
#                     f"Metric: {metric_name} ({stat_type}) was {round(avg_stat_value, 2)}, triggering rule ({rule['condition']}).\n"
#                     f"Recommendation: {action}\n"
#                     f"Current Instance: {current_instance_class} @ ${current_hourly_price:.4f}/hr\n"
#                 )
#                 if suggested_instance and new_hourly_price > 0:
#                     full_rec_console += f"Suggested Instance: {suggested_instance} @ ${new_hourly_price:.4f}/hr\n"
#                 full_rec_console += f"{cost_impact}\n\n{llm_text}"

#                 print(f"\n✅ Generated Recommendation for [User {userid}] - {arn}")
#                 print(full_rec_console)
                
#                 # --- Assemble clean recommendation for database ---
#                 db_recommendation_text = f"Metric: {metric_name}\n\n{llm_text}"
                
#                 db_rec_session = SessionLocal()
#                 insert_or_update(
#                     db=db_rec_session, userid=userid, resource_type=resource_type, arn=arn,
#                     recommendation_text=db_recommendation_text
#                 )
#                 db_rec_session.close()


# # --- Execution ---
# if __name__ == "__main__":
#     print("--- Starting Cloud Cost Advisor ---")
    
#     print("\n[Step 1/3] Fetching resource ARNs from database...")
#     arns_by_user = fetch_arns_grouped_by_user_id()
#     if not arns_by_user:
#         print("No ARNs found. Exiting.")
#     else:
#         print(f"Found resources for {len(arns_by_user)} user(s).")

#         print("\n[Step 2/3] Collecting CloudWatch metrics for all resources...")
#         collect_all_metrics(arns_by_user)
        
#         print("\n[Step 3/3] Generating recommendations based on collected data...")
#         generate_recommendations()
        
#     print("\n--- Advisor run complete. ---")

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

# # --- EC2 Instance Sizing Maps ---
# INSTANCE_DOWNSIZE_MAP = {
#     # T3 family
#     "t3.2xlarge": "t3.xlarge", "t3.xlarge": "t3.large", "t3.large": "t3.medium",
#     "t3.medium": "t3.small", "t3.small": "t3.micro", "t3.micro": "t3.nano",
#     # T2 family
#     "t2.2xlarge": "t2.xlarge", "t2.xlarge": "t2.large", "t2.large": "t2.medium",
#     "t2.medium": "t2.small", "t2.small": "t2.micro", "t2.micro": "t3.nano",
#     # M5 family
#     "m5.24xlarge": "m5.12xlarge", "m5.12xlarge": "m5.4xlarge", "m5.4xlarge": "m5.2xlarge",
#     "m5.2xlarge": "m5.xlarge", "m5.xlarge": "m5.large", "m5.large": "t3.large",
# }

# INSTANCE_UPSIZE_MAP = {
#     # T3 family
#     "t3.nano": "t3.micro", "t3.micro": "t3.small", "t3.small": "t3.medium",
#     "t3.medium": "t3.large", "t3.large": "t3.xlarge", "t3.xlarge": "t3.2xlarge",
#     # T2 family
#     "t2.nano": "t2.micro", "t2.micro": "t2.small", "t2.small": "t2.medium",
#     "t2.medium": "t2.large", "t2.large": "t2.xlarge", "t2.xlarge": "t2.2xlarge",
#     # M5 family
#     "m5.large": "m5.xlarge", "m5.xlarge": "m5.2xlarge", "m5.2xlarge": "m5.4xlarge",
#     "m5.4xlarge": "m5.12xlarge", "m5.12xlarge": "m5.24xlarge",
# }

# # --- RDS Instance Sizing Maps (New) ---
# RDS_INSTANCE_DOWNSIZE_MAP = {
#     # T3 DB Instances
#     "db.t3.2xlarge": "db.t3.xlarge", "db.t3.xlarge": "db.t3.large",
#     "db.t3.large": "db.t3.medium", "db.t3.medium": "db.t3.small", "db.t3.small": "db.t3.micro",
#     # M5 DB Instances
#     "db.m5.24xlarge": "db.m5.12xlarge", "db.m5.12xlarge": "db.m5.8xlarge",
#     "db.m5.8xlarge": "db.m5.4xlarge", "db.m5.4xlarge": "db.m5.2xlarge",
#     "db.m5.2xlarge": "db.m5.xlarge", "db.m5.xlarge": "db.m5.large",
# }

# RDS_INSTANCE_UPSIZE_MAP = {
#     # T3 DB Instances
#     "db.t3.micro": "db.t3.small", "db.t3.small": "db.t3.medium", "db.t3.medium": "db.t3.large",
#     "db.t3.large": "db.t3.xlarge", "db.t3.xlarge": "db.t3.2xlarge",
#     # M5 DB Instances
#     "db.m5.large": "db.m5.xlarge", "db.m5.xlarge": "db.m5.2xlarge",
#     "db.m5.2xlarge": "db.m5.4xlarge", "db.m5.4xlarge": "db.m5.8xlarge",
#     "db.m5.8xlarge": "db.m5.12xlarge", "db.m5.12xlarge": "db.m5.24xlarge",
# }

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

# def get_resource_hourly_price(service: str, resource_info: dict) -> float:
#     """
#     Fetches the on-demand hourly price for an AWS resource with multiple fallbacks.
#     Returns -1.0 if pricing cannot be found.
#     """
#     try:
#         pricing_client = boto3.client("pricing", region_name="us-east-1")
#         location = resource_info.get("location", "US East (N. Virginia)")
#         instance_type = resource_info.get("instance_type")

#         if not all([service, instance_type, location]):
#             print("❌ Missing service, instance_type, or location for pricing.")
#             return -1.0

#         base_filters = [
#             {"Type": "TERM_MATCH", "Field": "location", "Value": location},
#             {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
#         ]
        
#         service_code = ""
#         initial_filters = []
#         if service == "EC2":
#             service_code = "AmazonEC2"
#             initial_filters = base_filters + [
#                 {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": resource_info.get("operatingSystem", "Linux")},
#                 {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
#                 {"Type": "TERM_MATCH", "Field": "tenancy", "Value": resource_info.get("tenancy", "Shared")},
#                 {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"}
#             ]
#         elif service == "RDS":
#             service_code = "AmazonRDS"
#             engine_map = {"postgres": "PostgreSQL", "mysql": "MySQL"}
#             db_engine = engine_map.get(resource_info.get("engine"), "MySQL")
            
#             initial_filters = base_filters + [
#                 {"Type": "TERM_MATCH", "Field": "databaseEngine", "Value": db_engine},
#                 {"Type": "TERM_MATCH", "Field": "deploymentOption", "Value": "Single-AZ"}
#             ]
#         else:
#             print(f"⚠️ Pricing not implemented for service: {service}")
#             return -1.0

#         # Try the full filter set first
#         print(f"🔎 Fetching pricing for {service} {instance_type} in {location}")
#         response = pricing_client.get_products(ServiceCode=service_code, Filters=initial_filters, MaxResults=1)

#         # Fallback 1: For EC2, remove 'capacitystatus'
#         if not response.get("PriceList") and service == "EC2":
#             print(f"⚠️ No pricing data with 'capacitystatus' for {instance_type}. Retrying without it...")
#             fallback_filters_1 = [f for f in initial_filters if f["Field"] != "capacitystatus"]
#             response = pricing_client.get_products(ServiceCode=service_code, Filters=fallback_filters_1, MaxResults=1)

#         # Fallback 2: For EC2, also remove 'preInstalledSw'
#         if not response.get("PriceList") and service == "EC2":
#             print(f"⚠️ Still no pricing data. Retrying without 'preInstalledSw' as well...")
#             fallback_filters_2 = [f for f in initial_filters if f["Field"] not in ["capacitystatus", "preInstalledSw"]]
#             response = pricing_client.get_products(ServiceCode=service_code, Filters=fallback_filters_2, MaxResults=1)
            
#         # Fallback 3: For EC2, use only the most basic filters as a last resort
#         if not response.get("PriceList") and service == "EC2":
#             print(f"⚠️ Last resort. Retrying with only location and instance type for {instance_type}...")
#             response = pricing_client.get_products(ServiceCode=service_code, Filters=base_filters, MaxResults=1)

#         if not response.get("PriceList"):
#             print(f"❌ All fallbacks failed. No pricing data found for {instance_type} in {location}.")
#             return -1.0

#         price_item = json.loads(response["PriceList"][0])
#         terms = price_item.get("terms", {}).get("OnDemand", {})
#         for term in terms.values():
#             for dim in term.get("priceDimensions", {}).values():
#                 price = float(dim["pricePerUnit"]["USD"])
#                 print(f"✅ Found price for {instance_type}: ${price:.4f}/hour")
#                 return price

#         print(f"⚠️ Price dimensions not found for {instance_type}.")
#         return -1.0

#     except Exception as e:
#         print(f"❌ Failed to fetch pricing for {resource_info.get('instance_type')}: {e}")
#         return -1.0

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
                db_recommendation_text = f"Metric: {metric_name}\n\n{llm_text}"
                
                db_rec_session = SessionLocal()
                try:
                    insert_or_update(
                        db=db_rec_session, userid=userid, resource_type=resource_type, arn=arn,
                        recommendation_text=db_recommendation_text
                    )
                except Exception as e:
                    print(f"❌ Error saving recommendation to database: {e}")
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