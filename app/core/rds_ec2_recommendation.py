import boto3
import json
import os
import re
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv
from collections import defaultdict
from sqlalchemy import or_
from datetime import datetime, timedelta
from statistics import mean

# --- Database Imports ---
from app.database import SessionLocal
from app.models.infrastructure_inventory import InfrastructureInventory
from app.db.metrics_collector import create_or_update_metrics
from app.db.recommendation import insert_or_update


from openai import OpenAI

load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")
if openai_api_key:
    openai_client = OpenAI(api_key=openai_api_key)
else:
    print("⚠️ OpenAI API key not found. LLM recommendations will be disabled.")
    openai_client = None

try:
    with open("app/core/cloudwatch_metrics_config.json", 'r') as f:
        METRICS_CONFIG = json.load(f)
    print("✅ Successfully loaded cloudwatch_metrics_config.json")
except FileNotFoundError:
    print("❌ cloudwatch_metrics_config.json not found. Metrics collection will be disabled.")
    METRICS_CONFIG = {}
except json.JSONDecodeError:
    print("❌ Error decoding cloudwatch_metrics_config.json. Please check the file format.")
    METRICS_CONFIG = {}

try:
    with open("app/core/cloudwatch_recommendation_rules.json", 'r') as f:
        RECOMMENDATION_RULES = json.load(f)
    print("✅ Successfully loaded cloudwatch_recommendation_rules.json")
except FileNotFoundError:
    print("❌ cloudwatch_recommendation_rules.json not found. Recommendations will be disabled.")
    RECOMMENDATION_RULES = {}
except json.JSONDecodeError:
    print("❌ Error decoding cloudwatch_recommendation_rules.json. Please check the file format.")
    RECOMMENDATION_RULES = {}



# EC2 Instance Downsize Map - Cross-family optimized for cost efficiency
INSTANCE_DOWNSIZE_MAP = {
    # T3 Family
    "t3.2xlarge": "t3.xlarge", 
    "t3.xlarge": "t3.large", 
    "t3.large": "t3.medium", 
    "t3.medium": "t3.small", 
    "t3.small": "t3.micro", 
    "t3.micro": "t3.nano",
    "t3.nano": "t4g.nano",
    
    # T2 to T4g (ARM for better cost-performance)
    "t2.2xlarge": "t3.xlarge", 
    "t2.xlarge": "t3.large", 
    "t2.large": "t3.medium", 
    "t2.medium": "t3.small", 
    "t2.small": "t3.micro", 
    "t2.micro": "t4g.nano", 
    "t2.nano": "t4g.nano",
    
    # T4g Family (ARM-based)
    "t4g.2xlarge": "t4g.xlarge", 
    "t4g.xlarge": "t4g.large", 
    "t4g.large": "t4g.medium", 
    "t4g.medium": "t4g.small", 
    "t4g.small": "t4g.micro", 
    "t4g.micro": "t4g.nano",
    
    # M5 Family - Cross-family to burstable for cost savings
    "m5.24xlarge": "m5.12xlarge", 
    "m5.12xlarge": "m5.4xlarge", 
    "m5.4xlarge": "m5.2xlarge", 
    "m5.2xlarge": "m5.xlarge", 
    "m5.xlarge": "m5.large", 
    "m5.large": "t3.xlarge",
    "m5.medium": "t3.large",
    "m5.small": "t3.medium",
    
    # M6i Family (Latest generation)
    "m6i.32xlarge": "m6i.16xlarge",
    "m6i.16xlarge": "m6i.8xlarge",
    "m6i.8xlarge": "m6i.4xlarge",
    "m6i.4xlarge": "m6i.2xlarge",
    "m6i.2xlarge": "m6i.xlarge",
    "m6i.xlarge": "m6i.large",
    "m6i.large": "m5.large",
    "m6i.medium": "t3.large",
    
    # M6a Family (AMD-based)
    "m6a.48xlarge": "m6a.24xlarge",
    "m6a.24xlarge": "m6a.12xlarge",
    "m6a.12xlarge": "m6a.4xlarge",
    "m6a.4xlarge": "m6a.2xlarge",
    "m6a.2xlarge": "m6a.xlarge",
    "m6a.xlarge": "m6a.large",
    "m6a.large": "m5.large",
    "m6a.medium": "t3.large",
    
    # M7i Family (7th generation)
    "m7i.48xlarge": "m7i.24xlarge",
    "m7i.24xlarge": "m7i.12xlarge",
    "m7i.12xlarge": "m7i.4xlarge",
    "m7i.4xlarge": "m7i.2xlarge",
    "m7i.2xlarge": "m7i.xlarge",
    "m7i.xlarge": "m7i.large",
    "m7i.large": "m6i.large",
    
    # C5 Family - Cross-family to burstable
    "c5.24xlarge": "c5.12xlarge", 
    "c5.12xlarge": "c5.4xlarge", 
    "c5.4xlarge": "c5.2xlarge", 
    "c5.2xlarge": "c5.xlarge", 
    "c5.xlarge": "c5.large", 
    "c5.large": "t3.xlarge",
    "c5.medium": "t3.large",
    
    # C6i Family (Latest compute)
    "c6i.32xlarge": "c6i.16xlarge",
    "c6i.16xlarge": "c6i.8xlarge",
    "c6i.8xlarge": "c6i.4xlarge",
    "c6i.4xlarge": "c6i.2xlarge",
    "c6i.2xlarge": "c6i.xlarge",
    "c6i.xlarge": "c6i.large",
    "c6i.large": "c5.large",
    "c6i.medium": "t3.large",
    
    # C6a Family (AMD compute)
    "c6a.48xlarge": "c6a.24xlarge",
    "c6a.24xlarge": "c6a.12xlarge",
    "c6a.12xlarge": "c6a.4xlarge",
    "c6a.4xlarge": "c6a.2xlarge",
    "c6a.2xlarge": "c6a.xlarge",
    "c6a.xlarge": "c6a.large",
    "c6a.large": "c5.large",
    
    # C7i Family (7th generation compute)
    "c7i.48xlarge": "c7i.24xlarge",
    "c7i.24xlarge": "c7i.12xlarge",
    "c7i.12xlarge": "c7i.4xlarge",
    "c7i.4xlarge": "c7i.2xlarge",
    "c7i.2xlarge": "c7i.xlarge",
    "c7i.xlarge": "c7i.large",
    "c7i.large": "c6i.large",
    
    # R5 Family - Cross-family when high memory not needed
    "r5.24xlarge": "r5.12xlarge",
    "r5.12xlarge": "r5.4xlarge",
    "r5.4xlarge": "r5.2xlarge",
    "r5.2xlarge": "r5.xlarge",
    "r5.xlarge": "r5.large",
    "r5.large": "m5.xlarge",
    
    # R6i Family (Latest memory)
    "r6i.32xlarge": "r6i.16xlarge",
    "r6i.16xlarge": "r6i.8xlarge",
    "r6i.8xlarge": "r6i.4xlarge",
    "r6i.4xlarge": "r6i.2xlarge",
    "r6i.2xlarge": "r6i.xlarge",
    "r6i.xlarge": "r6i.large",
    "r6i.large": "r5.large",
    
    # R6a Family (AMD memory)
    "r6a.48xlarge": "r6a.24xlarge",
    "r6a.24xlarge": "r6a.12xlarge",
    "r6a.12xlarge": "r6a.4xlarge",
    "r6a.4xlarge": "r6a.2xlarge",
    "r6a.2xlarge": "r6a.xlarge",
    "r6a.xlarge": "r6a.large",
    "r6a.large": "r5.large",
    
    # R7i Family (7th generation memory)
    "r7i.48xlarge": "r7i.24xlarge",
    "r7i.24xlarge": "r7i.12xlarge",
    "r7i.12xlarge": "r7i.4xlarge",
    "r7i.4xlarge": "r7i.2xlarge",
    "r7i.2xlarge": "r7i.xlarge",
    "r7i.xlarge": "r7i.large",
    "r7i.large": "r6i.large",
    
    # X1e Family (High memory) - Cross-family
    "x1e.32xlarge": "x1e.16xlarge",
    "x1e.16xlarge": "x1e.8xlarge",
    "x1e.8xlarge": "x1e.4xlarge",
    "x1e.4xlarge": "x1e.2xlarge",
    "x1e.2xlarge": "x1e.xlarge",
    "x1e.xlarge": "r5.2xlarge",
    
    # I3 Family (Storage optimized)
    "i3.16xlarge": "i3.8xlarge",
    "i3.8xlarge": "i3.4xlarge",
    "i3.4xlarge": "i3.2xlarge",
    "i3.2xlarge": "i3.xlarge",
    "i3.xlarge": "i3.large",
    "i3.large": "m5.large",
    
    # I4i Family (Latest storage)
    "i4i.32xlarge": "i4i.16xlarge",
    "i4i.16xlarge": "i4i.8xlarge",
    "i4i.8xlarge": "i4i.4xlarge",
    "i4i.4xlarge": "i4i.2xlarge",
    "i4i.2xlarge": "i4i.xlarge",
    "i4i.xlarge": "i4i.large",
    "i4i.large": "i3.large",
}

# EC2 Instance Upsize Map - Cross-family optimized for performance
INSTANCE_UPSIZE_MAP = {
    # T3 Family - Cross-family to general purpose for consistent performance
    "t4g.nano": "t3.nano", 
    "t3.nano": "t3.micro", 
    "t3.micro": "t3.small", 
    "t3.small": "t3.medium", 
    "t3.medium": "t3.large", 
    "t3.large": "t3.xlarge", 
    "t3.xlarge": "t3.2xlarge",
    "t3.2xlarge": "m6i.large",
    
    # T2 to T4g (ARM migration)
    "t2.nano": "t4g.nano", 
    "t2.micro": "t4g.micro", 
    "t2.small": "t4g.small", 
    "t2.medium": "t4g.medium", 
    "t2.large": "t4g.large", 
    "t2.xlarge": "t4g.xlarge", 
    "t2.2xlarge": "t4g.2xlarge",
    
    # T4g Family - Cross-family when burstable limits reached
    "t4g.nano": "t4g.micro", 
    "t4g.micro": "t4g.small", 
    "t4g.small": "t4g.medium", 
    "t4g.medium": "t4g.large", 
    "t4g.large": "t4g.xlarge", 
    "t4g.xlarge": "t4g.2xlarge",
    "t4g.2xlarge": "m6i.large",
    
    # M5 to newer generations
    "m5.large": "m5.xlarge", 
    "m5.xlarge": "m5.2xlarge", 
    "m5.2xlarge": "m5.4xlarge", 
    "m5.4xlarge": "m5.12xlarge", 
    "m5.12xlarge": "m5.24xlarge",
    "m5.24xlarge": "m6i.32xlarge",
    "m5.medium": "m6i.large",
    "m5.small": "m6i.medium",
    
    # M6i Family (Preferred general purpose)
    "m6i.large": "m6i.xlarge",
    "m6i.xlarge": "m6i.2xlarge",
    "m6i.2xlarge": "m6i.4xlarge",
    "m6i.4xlarge": "m6i.8xlarge",
    "m6i.8xlarge": "m6i.16xlarge",
    "m6i.16xlarge": "m6i.32xlarge",
    "m6i.32xlarge": "m7i.48xlarge",
    "m6i.medium": "m6i.large",
    
    # M6a Family (AMD)
    "m6a.large": "m6a.xlarge",
    "m6a.xlarge": "m6a.2xlarge",
    "m6a.2xlarge": "m6a.4xlarge",
    "m6a.4xlarge": "m6a.12xlarge",
    "m6a.12xlarge": "m6a.24xlarge",
    "m6a.24xlarge": "m6a.48xlarge",
    "m6a.medium": "m6a.large",
    
    # M7i Family (Latest generation)
    "m7i.large": "m7i.xlarge",
    "m7i.xlarge": "m7i.2xlarge",
    "m7i.2xlarge": "m7i.4xlarge",
    "m7i.4xlarge": "m7i.12xlarge",
    "m7i.12xlarge": "m7i.24xlarge",
    "m7i.24xlarge": "m7i.48xlarge",
    
    # C5 to newer generations
    "c5.large": "c5.xlarge", 
    "c5.xlarge": "c5.2xlarge", 
    "c5.2xlarge": "c5.4xlarge", 
    "c5.4xlarge": "c5.12xlarge", 
    "c5.12xlarge": "c5.24xlarge",
    "c5.24xlarge": "c6i.32xlarge",
    "c5.medium": "c6i.large",
    
    # C6i Family (Preferred compute)
    "c6i.large": "c6i.xlarge",
    "c6i.xlarge": "c6i.2xlarge",
    "c6i.2xlarge": "c6i.4xlarge",
    "c6i.4xlarge": "c6i.8xlarge",
    "c6i.8xlarge": "c6i.16xlarge",
    "c6i.16xlarge": "c6i.32xlarge",
    "c6i.32xlarge": "c7i.48xlarge",
    "c6i.medium": "c6i.large",
    
    # C6a Family (AMD compute)
    "c6a.large": "c6a.xlarge",
    "c6a.xlarge": "c6a.2xlarge",
    "c6a.2xlarge": "c6a.4xlarge",
    "c6a.4xlarge": "c6a.12xlarge",
    "c6a.12xlarge": "c6a.24xlarge",
    "c6a.24xlarge": "c6a.48xlarge",
    
    # C7i Family (Latest compute)
    "c7i.large": "c7i.xlarge",
    "c7i.xlarge": "c7i.2xlarge",
    "c7i.2xlarge": "c7i.4xlarge",
    "c7i.4xlarge": "c7i.12xlarge",
    "c7i.12xlarge": "c7i.24xlarge",
    "c7i.24xlarge": "c7i.48xlarge",
    
    # R5 to newer generations
    "r5.large": "r5.xlarge", 
    "r5.xlarge": "r5.2xlarge", 
    "r5.2xlarge": "r5.4xlarge", 
    "r5.4xlarge": "r5.12xlarge", 
    "r5.12xlarge": "r5.24xlarge",
    "r5.24xlarge": "r6i.32xlarge",
    
    # R6i Family (Preferred memory)
    "r6i.large": "r6i.xlarge",
    "r6i.xlarge": "r6i.2xlarge",
    "r6i.2xlarge": "r6i.4xlarge",
    "r6i.4xlarge": "r6i.8xlarge",
    "r6i.8xlarge": "r6i.16xlarge",
    "r6i.16xlarge": "r6i.32xlarge",
    "r6i.32xlarge": "r7i.48xlarge",
    
    # R6a Family (AMD memory)
    "r6a.large": "r6a.xlarge",
    "r6a.xlarge": "r6a.2xlarge",
    "r6a.2xlarge": "r6a.4xlarge",
    "r6a.4xlarge": "r6a.12xlarge",
    "r6a.12xlarge": "r6a.24xlarge",
    "r6a.24xlarge": "r6a.48xlarge",
    
    # R7i Family (Latest memory)
    "r7i.large": "r7i.xlarge",
    "r7i.xlarge": "r7i.2xlarge",
    "r7i.2xlarge": "r7i.4xlarge",
    "r7i.4xlarge": "r7i.12xlarge",
    "r7i.12xlarge": "r7i.24xlarge",
    "r7i.24xlarge": "r7i.48xlarge",
    
    # X1e Family (High memory)
    "x1e.xlarge": "x1e.2xlarge",
    "x1e.2xlarge": "x1e.4xlarge",
    "x1e.4xlarge": "x1e.8xlarge",
    "x1e.8xlarge": "x1e.16xlarge",
    "x1e.16xlarge": "x1e.32xlarge",
    
    # I3 Family (Storage)
    "i3.large": "i3.xlarge",
    "i3.xlarge": "i3.2xlarge",
    "i3.2xlarge": "i3.4xlarge",
    "i3.4xlarge": "i3.8xlarge",
    "i3.8xlarge": "i3.16xlarge",
    "i3.16xlarge": "i4i.32xlarge",
    
    # I4i Family (Latest storage)
    "i4i.large": "i4i.xlarge",
    "i4i.xlarge": "i4i.2xlarge",
    "i4i.2xlarge": "i4i.4xlarge",
    "i4i.4xlarge": "i4i.8xlarge",
    "i4i.8xlarge": "i4i.16xlarge",
    "i4i.16xlarge": "i4i.32xlarge",
}

# RDS Instance Downsize Map - Cross-family optimized
RDS_DOWNSIZE_MAP = {
    # T3 Family
    "db.t3.2xlarge": "db.t3.xlarge", 
    "db.t3.xlarge": "db.t3.large", 
    "db.t3.large": "db.t3.medium", 
    "db.t3.medium": "db.t3.small", 
    "db.t3.small": "db.t3.micro",
    "db.t3.micro": "db.t4g.micro",
    
    # T4g Family (ARM-based)
    "db.t4g.2xlarge": "db.t4g.xlarge",
    "db.t4g.xlarge": "db.t4g.large",
    "db.t4g.large": "db.t4g.medium",
    "db.t4g.medium": "db.t4g.small",
    "db.t4g.small": "db.t4g.micro",
    
    # M5 Family - Cross-family to burstable
    "db.m5.24xlarge": "db.m5.12xlarge", 
    "db.m5.12xlarge": "db.m5.8xlarge", 
    "db.m5.8xlarge": "db.m5.4xlarge", 
    "db.m5.4xlarge": "db.m5.2xlarge", 
    "db.m5.2xlarge": "db.m5.xlarge", 
    "db.m5.xlarge": "db.m5.large", 
    "db.m5.large": "db.t3.2xlarge",
    
    # M6i Family
    "db.m6i.32xlarge": "db.m6i.16xlarge",
    "db.m6i.16xlarge": "db.m6i.8xlarge",
    "db.m6i.8xlarge": "db.m6i.4xlarge",
    "db.m6i.4xlarge": "db.m6i.2xlarge",
    "db.m6i.2xlarge": "db.m6i.xlarge",
    "db.m6i.xlarge": "db.m6i.large",
    "db.m6i.large": "db.m5.large",
    
    # M6gd Family (ARM with SSD)
    "db.m6gd.16xlarge": "db.m6gd.8xlarge",
    "db.m6gd.8xlarge": "db.m6gd.4xlarge",
    "db.m6gd.4xlarge": "db.m6gd.2xlarge",
    "db.m6gd.2xlarge": "db.m6gd.xlarge",
    "db.m6gd.xlarge": "db.m6gd.large",
    "db.m6gd.large": "db.t4g.large",
    
    # R5 Family - Cross-family when high memory not needed
    "db.r5.24xlarge": "db.r5.12xlarge", 
    "db.r5.12xlarge": "db.r5.4xlarge", 
    "db.r5.4xlarge": "db.r5.2xlarge", 
    "db.r5.2xlarge": "db.r5.xlarge", 
    "db.r5.xlarge": "db.r5.large", 
    "db.r5.large": "db.m5.2xlarge",
    
    # R6i Family
    "db.r6i.32xlarge": "db.r6i.16xlarge",
    "db.r6i.16xlarge": "db.r6i.8xlarge",
    "db.r6i.8xlarge": "db.r6i.4xlarge",
    "db.r6i.4xlarge": "db.r6i.2xlarge",
    "db.r6i.2xlarge": "db.r6i.xlarge",
    "db.r6i.xlarge": "db.r6i.large",
    "db.r6i.large": "db.r5.large",
    
    # R6g Family (ARM memory optimized)
    "db.r6g.16xlarge": "db.r6g.8xlarge",
    "db.r6g.8xlarge": "db.r6g.4xlarge",
    "db.r6g.4xlarge": "db.r6g.2xlarge",
    "db.r6g.2xlarge": "db.r6g.xlarge",
    "db.r6g.xlarge": "db.r6g.large",
    "db.r6g.large": "db.t4g.xlarge",
    
    # X1e Family - Cross-family when extreme memory not needed
    "db.x1e.32xlarge": "db.x1e.16xlarge",
    "db.x1e.16xlarge": "db.x1e.8xlarge",
    "db.x1e.8xlarge": "db.x1e.4xlarge",
    "db.x1e.4xlarge": "db.x1e.2xlarge",
    "db.x1e.2xlarge": "db.x1e.xlarge",
    "db.x1e.xlarge": "db.r5.2xlarge",
    
    # X2g Family (ARM high memory)
    "db.x2g.16xlarge": "db.x2g.12xlarge",
    "db.x2g.12xlarge": "db.x2g.8xlarge",
    "db.x2g.8xlarge": "db.x2g.4xlarge",
    "db.x2g.4xlarge": "db.x2g.2xlarge",
    "db.x2g.2xlarge": "db.x2g.xlarge",
    "db.x2g.xlarge": "db.r6g.xlarge",
}

# RDS Instance Upsize Map - Cross-family optimized
RDS_UPSIZE_MAP = {
    # T3 Family - Cross-family for consistent performance
    "db.t3.micro": "db.t3.small", 
    "db.t3.small": "db.t3.medium", 
    "db.t3.medium": "db.t3.large", 
    "db.t3.large": "db.t3.xlarge", 
    "db.t3.xlarge": "db.t3.2xlarge", 
    "db.t3.2xlarge": "db.m6i.large",
    
    # T4g Family - Cross-family when burstable limits reached
    "db.t4g.micro": "db.t4g.small",
    "db.t4g.small": "db.t4g.medium",
    "db.t4g.medium": "db.t4g.large",
    "db.t4g.large": "db.t4g.xlarge",
    "db.t4g.xlarge": "db.t4g.2xlarge",
    "db.t4g.2xlarge": "db.m6gd.large",
    
    # M5 to newer generations
    "db.m5.large": "db.m5.xlarge", 
    "db.m5.xlarge": "db.m5.2xlarge", 
    "db.m5.2xlarge": "db.m5.4xlarge", 
    "db.m5.4xlarge": "db.m5.8xlarge", 
    "db.m5.8xlarge": "db.m5.12xlarge", 
    "db.m5.12xlarge": "db.m5.24xlarge",
    "db.m5.24xlarge": "db.m6i.32xlarge",
    
    # M6i Family (Preferred general purpose)
    "db.m6i.large": "db.m6i.xlarge",
    "db.m6i.xlarge": "db.m6i.2xlarge",
    "db.m6i.2xlarge": "db.m6i.4xlarge",
    "db.m6i.4xlarge": "db.m6i.8xlarge",
    "db.m6i.8xlarge": "db.m6i.16xlarge",
    "db.m6i.16xlarge": "db.m6i.32xlarge",
    
    # M6gd Family (ARM with SSD)
    "db.m6gd.large": "db.m6gd.xlarge",
    "db.m6gd.xlarge": "db.m6gd.2xlarge",
    "db.m6gd.2xlarge": "db.m6gd.4xlarge",
    "db.m6gd.4xlarge": "db.m6gd.8xlarge",
    "db.m6gd.8xlarge": "db.m6gd.16xlarge",
    
    # R5 to newer generations
    "db.r5.large": "db.r5.xlarge", 
    "db.r5.xlarge": "db.r5.2xlarge", 
    "db.r5.2xlarge": "db.r5.4xlarge", 
    "db.r5.4xlarge": "db.r5.12xlarge", 
    "db.r5.12xlarge": "db.r5.24xlarge",
    "db.r5.24xlarge": "db.r6i.32xlarge",
    
    # R6i Family (Preferred memory)
    "db.r6i.large": "db.r6i.xlarge",
    "db.r6i.xlarge": "db.r6i.2xlarge",
    "db.r6i.2xlarge": "db.r6i.4xlarge",
    "db.r6i.4xlarge": "db.r6i.8xlarge",
    "db.r6i.8xlarge": "db.r6i.16xlarge",
    "db.r6i.16xlarge": "db.r6i.32xlarge",
    
    # R6g Family (ARM memory optimized)
    "db.r6g.large": "db.r6g.xlarge",
    "db.r6g.xlarge": "db.r6g.2xlarge",
    "db.r6g.2xlarge": "db.r6g.4xlarge",
    "db.r6g.4xlarge": "db.r6g.8xlarge",
    "db.r6g.8xlarge": "db.r6g.16xlarge",
    
    # X1e Family (High memory)
    "db.x1e.xlarge": "db.x1e.2xlarge",
    "db.x1e.2xlarge": "db.x1e.4xlarge",
    "db.x1e.4xlarge": "db.x1e.8xlarge",
    "db.x1e.8xlarge": "db.x1e.16xlarge",
    "db.x1e.16xlarge": "db.x1e.32xlarge",
    
    # X2g Family (ARM high memory)
    "db.x2g.xlarge": "db.x2g.2xlarge",
    "db.x2g.2xlarge": "db.x2g.4xlarge",
    "db.x2g.4xlarge": "db.x2g.8xlarge",
    "db.x2g.8xlarge": "db.x2g.12xlarge",
    "db.x2g.12xlarge": "db.x2g.16xlarge",
}





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
-If the pricing data is not available then do not say i do not have have that data , Generate general action, impact and savings.
-**Do NOT**-use sentence like "but pricing information is not available." instead say a general sentence based on above info.

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



def get_boto3_session():
    """Create a boto3 session. Boto3 will automatically find credentials."""
    try:
        session = boto3.Session()
        if session.get_credentials() is None:
            raise NoCredentialsError("AWS credentials not found.")
        print("✅ AWS session created successfully.")
        return session
    except NoCredentialsError as e:
        raise e
    except Exception as e:
        raise Exception(f"Could not create Boto3 session. Error: {e}")

def fetch_arns_grouped_by_user_id():
    """Fetches EC2 and RDS instance ARNs from the database."""
    session = SessionLocal()
    try:
        result = defaultdict(list)
        records = session.query(InfrastructureInventory.user_id, InfrastructureInventory.arn).filter(
            or_(
                InfrastructureInventory.arn.like('arn:aws:ec2:%:instance/%'),
                InfrastructureInventory.arn.like('arn:aws:rds:%:%:db:%')
            )
        ).all()
        print(f"\nFound {len(records)} processable EC2/RDS records in the database.")
        for user_id, arn in records:
            if user_id in (5, 7):
                continue
            result[user_id].append(arn)
        return dict(result)
    finally:
        session.close()

def extract_instance_info_from_arn(arn):
    """Extract instance ID/identifier and region from ARN."""
    try:
        arn_parts = arn.split(':')
        service = arn_parts[2]
        region = arn_parts[3]
        if service == 'ec2' and 'instance/' in arn:
            return arn.split('/')[-1], region, 'EC2'
        elif service == 'rds' and arn_parts[5] == 'db':
            return arn_parts[-1], region, 'RDS'
        else:
            raise ValueError(f"Unsupported ARN type for service: {service}.")
    except (IndexError, ValueError) as e:
        raise ValueError(f"Invalid ARN format: {arn}. Error: {e}")

# --- Instance Description and Metrics ---
def describe_ec2_instance(instance_id, region, session):
    """Describe EC2 instance."""
    ec2_client = session.client('ec2', region_name=region)
    response = ec2_client.describe_instances(InstanceIds=[instance_id])
    if not response.get('Reservations') or not response['Reservations'][0].get('Instances'):
        raise ValueError(f"EC2 instance {instance_id} not found in region {region}.")
    instance = response['Reservations'][0]['Instances'][0]
    return {'ServiceType': 'EC2', 'InstanceType': instance['InstanceType'], 'Region': region, 'InstanceId': instance_id}

def describe_rds_instance(db_identifier, region, session):
    """Describe RDS instance."""
    rds_client = session.client('rds', region_name=region)
    response = rds_client.describe_db_instances(DBInstanceIdentifier=db_identifier)
    if not response.get('DBInstances'):
        raise ValueError(f"RDS instance {db_identifier} not found in region {region}.")
    db_instance = response['DBInstances'][0]
    engine_map = {'postgres': 'PostgreSQL', 'mysql': 'MySQL', 'mariadb': 'MariaDB'}
    return {
        'ServiceType': 'RDS', 'InstanceType': db_instance['DBInstanceClass'],
        'Engine': engine_map.get(db_instance['Engine'], db_instance['Engine']),
        'Region': region, 'DeploymentOption': 'Multi-AZ' if db_instance.get('MultiAZ') else 'Single-AZ',
        'AllocatedStorage': db_instance.get('AllocatedStorage', 0), 'StorageType': db_instance.get('StorageType', 'gp2'),
        'DBInstanceIdentifier': db_identifier
    }

def get_configured_cloudwatch_metrics(session, region, service_type, instance_id):
    """Fetches all metrics defined in the config file for a given resource."""
    if service_type not in METRICS_CONFIG:
        return {}
        
    cw_client = session.client('cloudwatch', region_name=region)
    collected_metrics = {}
    
    for metric_config in METRICS_CONFIG[service_type]["metrics"]:
        metric_name = metric_config["MetricName"]
        dimension_name = metric_config["Dimensions"][0]
        
        try:
            response = cw_client.get_metric_statistics(
                Namespace=metric_config["Namespace"],
                MetricName=metric_name,
                Dimensions=[{'Name': dimension_name, 'Value': instance_id}],
                StartTime=datetime.utcnow() - timedelta(days=14),
                EndTime=datetime.utcnow(),
                Period=86400,
                Statistics=metric_config["Statistics"]
            )
            
            datapoints = response.get('Datapoints', [])
            if not datapoints:
                print(f"  - No '{metric_name}' metrics found for {instance_id}.")
                continue

            for stat in metric_config["Statistics"]:
                # Calculate the mean of the statistic over the period
                stat_values = [dp[stat] for dp in datapoints if stat in dp]
                if stat_values:
                    avg_value = mean(stat_values)
                    collected_metrics[f"{metric_name}_{stat}"] = avg_value
                    print(f"  - {metric_name} ({stat}): {avg_value:.2f}")

        except ClientError as e:
            print(f"  - Could not fetch '{metric_name}' metrics for {instance_id}: {e}")
            
    return collected_metrics

# --- Pricing and Recommendation ---
def get_pricing_info(session, instance_details):
    """Unified function to get pricing."""
    service = instance_details['ServiceType']
    if service == 'EC2':
        return get_ec2_pricing(instance_details, session)
    elif service == 'RDS':
        return get_rds_pricing(instance_details, session)
    return None

def get_ec2_pricing(details, session):
    """Get EC2 pricing with fallbacks."""
    pricing_client = session.client('pricing', region_name='us-east-1')
    
    # Base filters that apply to all queries
    base_filters = [
        {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': details['InstanceType']},
        {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': details['Region']},
        {'Type': 'TERM_MATCH', 'Field': 'marketoption', 'Value': 'OnDemand'}
    ]
    
    # Most specific filter set
    full_filters = base_filters + [
        {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'},
        {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'},
        {'Type': 'TERM_MATCH', 'Field': 'preInstalledSw', 'Value': 'NA'},
        {'Type': 'TERM_MATCH', 'Field': 'capacitystatus', 'Value': 'Used'}
    ]

    response = pricing_client.get_products(ServiceCode='AmazonEC2', Filters=full_filters, MaxResults=1)

    # Fallback 1: Remove capacitystatus and preInstalledSw, which can be problematic
    if not response.get('PriceList'):
        print(f"  - Retrying price lookup for {details['InstanceType']} with broader filters...")
        fallback_filters_1 = base_filters + [
            {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'},
            {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'},
        ]
        response = pricing_client.get_products(ServiceCode='AmazonEC2', Filters=fallback_filters_1, MaxResults=1)

    # Fallback 2: Last resort, use only the most basic filters
    if not response.get('PriceList'):
        print(f"  - Last resort price lookup for {details['InstanceType']}...")
        response = pricing_client.get_products(ServiceCode='AmazonEC2', Filters=base_filters, MaxResults=1)

    if not response.get('PriceList'):
        print(f"  - Warning: All fallbacks failed. No EC2 pricing data found for {details['InstanceType']}.")
        return None
        
    price_data = json.loads(response['PriceList'][0])
    terms = price_data['terms']['OnDemand']
    price_info = list(list(terms.values())[0]['priceDimensions'].values())[0]
    return {'compute_hourly': float(price_info['pricePerUnit']['USD']), 'storage_monthly': 0}

def get_rds_pricing(details, session):
    """Get RDS pricing."""
    pricing_client = session.client('pricing', region_name='us-east-1')
    filters = [
        {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': details['InstanceType']},
        {'Type': 'TERM_MATCH', 'Field': 'databaseEngine', 'Value': details['Engine']},
        {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': details['Region']},
        {'Type': 'TERM_MATCH', 'Field': 'deploymentOption', 'Value': details['DeploymentOption']}
    ]
    response = pricing_client.get_products(ServiceCode='AmazonRDS', Filters=filters, MaxResults=1)
    if not response.get('PriceList'):
        print(f"  - Warning: No RDS compute pricing found for {details['InstanceType']}.")
        return None
    price_data = json.loads(response['PriceList'][0])
    terms = price_data['terms']['OnDemand']
    price_info = list(list(terms.values())[0]['priceDimensions'].values())[0]
    compute_hourly = float(price_info['pricePerUnit']['USD'])
    storage_monthly = get_rds_storage_pricing(details, session)
    return {'compute_hourly': compute_hourly, 'storage_monthly': storage_monthly}

def get_rds_storage_pricing(details, session):
    """Get RDS storage pricing."""
    if details['AllocatedStorage'] <= 0: return 0.0
    pricing_client = session.client('pricing', region_name='us-east-1')
    filters = [
        {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Database Storage'},
        {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': details['Region']},
        {'Type': 'TERM_MATCH', 'Field': 'volumeApiName', 'Value': details['StorageType']}
    ]
    response = pricing_client.get_products(ServiceCode='AmazonRDS', Filters=filters, MaxResults=1)
    if not response.get('PriceList'): return 0.0
    price_data = json.loads(response['PriceList'][0])
    terms = price_data['terms']['OnDemand']
    price_per_gb = float(list(list(terms.values())[0]['priceDimensions'].values())[0]['pricePerUnit']['USD'])
    return price_per_gb * details['AllocatedStorage']

def generate_recommendations(instance_details, collected_metrics):
    """Generates recommendations by evaluating metrics against rules from the JSON config."""
    service_type = instance_details['ServiceType']
    instance_type = instance_details['InstanceType']
    
    if service_type not in RECOMMENDATION_RULES:
        return None, None

    for metric_name, rules in RECOMMENDATION_RULES[service_type].items():
        for rule in rules:
            stat = rule["stat"]
            metric_key = f"{metric_name}_{stat}"
            
            if metric_key in collected_metrics:
                metric_value = collected_metrics[metric_key]
                condition = rule["condition"]
                
                # Simple parser for the condition string like "<=20"
                match = re.match(r"([<>=!]+)\s*(\d+\.?\d*)", condition)
                if match:
                    operator, value = match.groups()
                    value = float(value)
                    
                    if (operator == '<=' and metric_value <= value) or \
                       (operator == '>=' and metric_value >= value) or \
                       (operator == '<' and metric_value < value) or \
                       (operator == '>' and metric_value > value):
                        
                        action = rule["recommendation"]
                        if action in ["Downsize", "Upsize"]:
                            suggestion_map = (INSTANCE_DOWNSIZE_MAP if action == "Downsize" else INSTANCE_UPSIZE_MAP) if service_type == 'EC2' else (RDS_DOWNSIZE_MAP if action == "Downsize" else RDS_UPSIZE_MAP)
                            suggested_type = suggestion_map.get(instance_type)
                            if suggested_type:
                                print(f"  - Recommendation Triggered: {action} to {suggested_type} based on {metric_key} ({metric_value:.2f})")
                                return action, suggested_type
    return None, None

# --- Display and Main ---
def display_results(details, current_pricing, recommendation=None):
    """Displays the final details, costs, and any recommendations."""
    service_type = details['ServiceType']
    print(f"\n📋 {service_type} Instance Details:")
    print(f"  - Identifier: {details.get('InstanceId') or details.get('DBInstanceIdentifier')}")
    print(f"  - Type: {details['InstanceType']}")
    print(f"  - Region: {details['Region']}")
    
    current_compute_monthly = current_pricing['compute_hourly'] * 730
    current_total_monthly = current_compute_monthly + current_pricing.get('storage_monthly', 0)
    
    print("\n💵 Current Estimated Cost:")
    print(f"  - Compute: ${current_compute_monthly:,.2f}/month (${current_pricing['compute_hourly']:.4f}/hr)")
    if service_type == 'RDS':
        print(f"  - Storage: ${current_pricing['storage_monthly']:,.2f}/month")
    print(f"  - Total: ${current_total_monthly:,.2f}/month")

    if recommendation:
        action, new_type, new_pricing = recommendation
        new_compute_monthly = new_pricing['compute_hourly'] * 730
        new_total_monthly = new_compute_monthly + current_pricing.get('storage_monthly', 0)
        annual_savings = (current_total_monthly - new_total_monthly) * 12
        
        print(f"\n💡 Rightsizing Recommendation: {action} to {new_type}")
        print("   ---------------------------------")
        print(f"  - New Compute Cost: ${new_compute_monthly:,.2f}/month (${new_pricing['compute_hourly']:.4f}/hr)")
        print(f"  - New Total Cost: ${new_total_monthly:,.2f}/month")
        if annual_savings > 0:
            annual_cost = current_total_monthly * 12
            percent_savings = (annual_savings / annual_cost) * 100 if annual_cost > 0 else 0
            print(f"  - ✅ Estimated Annual Savings: ${annual_savings:,.2f} ({percent_savings:.1f}%)")
        else:
            print(f"  - ⚠️ Estimated Annual Cost Increase: ${abs(annual_savings):,.2f}")


def main():
    """Main function to fetch ARNs, get metrics, and provide cost/rightsizing recommendations."""
    try:
        session = get_boto3_session()
        arns_by_user = fetch_arns_grouped_by_user_id()
        if not arns_by_user:
            print("\nNo processable ARNs found. Exiting.")
            return

        print("\n==================================================")
        print("      STARTING AWS COST & RIGHTSIZING ADVISOR     ")
        print("==================================================")

        for user_id, arns in arns_by_user.items():
            print(f"\n\n--- Processing User ID: {user_id} ---")
            for arn in arns:
                try:
                    print(f"\n🔍 Processing ARN: {arn}")
                    instance_id, region, service_type = extract_instance_info_from_arn(arn)

                    describe_func = describe_ec2_instance if service_type == 'EC2' else describe_rds_instance
                    instance_details = describe_func(instance_id, region, session)

                    current_pricing = get_pricing_info(session, instance_details)
                    if not current_pricing:
                        print(f"  - Skipping {arn} as current pricing could not be determined.")
                        continue

                    collected_metrics = get_configured_cloudwatch_metrics(session, region, service_type, instance_id)

                    # ✅ Save to metrics_collection
                    if collected_metrics:
                        db = SessionLocal()
                        try:
                            create_or_update_metrics(
                                db=db,
                                userid=user_id,
                                arn=arn,
                                resource_type=service_type,
                                metrics_data=collected_metrics,
                                additional_info=instance_details
                            )
                        finally:
                            db.close()

                    # Proceed with recommendation
                    action, new_type = generate_recommendations(instance_details, collected_metrics)

                    recommendation_package = None
                    if action and new_type:
                        new_instance_details = instance_details.copy()
                        new_instance_details['InstanceType'] = new_type
                        new_pricing = get_pricing_info(session, new_instance_details)

                        if new_pricing:
                            recommendation_package = (action, new_type, new_pricing)

                            # 💡 LLM Recommendation Generation
                            current_total_annual = (current_pricing["compute_hourly"] * 24 * 365) + (current_pricing.get("storage_monthly", 0) * 12)
                            new_total_annual = (new_pricing["compute_hourly"] * 24 * 365) + (new_pricing.get("storage_monthly", 0) * 12)
                            savings = max(current_total_annual - new_total_annual, 0)
                            percent_savings = (savings / current_total_annual) * 100 if current_total_annual > 0 else 0

                            llm_text = generate_llm_recommendation(
                                resource_display_name=f"AWS {service_type}",
                                instance_type=instance_details["InstanceType"],
                                suggested_instance=new_type,
                                cost_hourly=new_pricing["compute_hourly"],
                                cost_saving=savings,
                                percent_saving=percent_savings
                            )

                            
                            action_text = impact_text = savings_text = None
                            try:
                                match = re.search(r"\d*\.*\s*Action:\s*(.+?)\n+\d*\.*\s*Impact:\s*(.+?)\n+\d*\.*\s*Savings:\s*(.+)", llm_text, re.DOTALL | re.IGNORECASE)
                                if match:
                                    action_text =match.group(1).strip()
                                    impact_text = match.group(2).strip()
                                    savings_text = match.group(3).strip()
                            except Exception as e:
                                print(f"⚠️ Failed to parse LLM response: {e}")


                            # 📝 Save to recommendation table
                            db = SessionLocal()
                            try:
                                insert_or_update(
                                    db=db,
                                    userid=user_id,
                                    resource_type=service_type,
                                    arn=arn,
                                    recommendation_text=llm_text,
                                    action=action_text,
                                    impact=impact_text,
                                    savings=savings_text
                                )
                            finally:
                                db.close()

                    display_results(instance_details, current_pricing, recommendation_package)

                except (ValueError, ClientError) as e:
                    print(f"❌ Error processing ARN {arn}: {e}")
                finally:
                    print("--------------------------------------------------")

    except NoCredentialsError as e:
        print(f"\n❌ AWS Credentials Error: {e}")
    except Exception as e:
        print(f"\n❌ An unexpected error occurred in the main process: {e}")



if __name__ == "__main__":
    main()
