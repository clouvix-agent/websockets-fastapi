import boto3
import json

# Hardcoded AWS credentials


pricing = boto3.client(
    'pricing',
    region_name='us-east-1',
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY
)

def get_rds_pricing():
    paginator = pricing.get_paginator('get_products')
    results = []
    filters = [
        {'Type': 'TERM_MATCH', 'Field': 'serviceCode', 'Value': 'AmazonRDS'}
        # Removed restrictive filters to get more data
    ]
    
    page_count = 0
    max_pages = 30  # Reduced for faster testing
    
    for page in paginator.paginate(ServiceCode='AmazonRDS', Filters=filters, MaxResults=100):
        page_count += 1
        print(f"Processing page {page_count} with {len(page['PriceList'])} items...")
        
        # Safety break
        if page_count > max_pages:
            print(f"Reached maximum page limit ({max_pages}), stopping...")
            break
        
        for price_item in page['PriceList']:
            item = json.loads(price_item)
            
            # Extract product attributes
            attrs = item.get('product', {}).get('attributes', {})
            instance_type = attrs.get('instanceType')
            location = attrs.get('location', '')
            
            # Skip items without instance type OR not from US East regions
            if not instance_type or 'US East' not in location:
                continue
            
            # Extract On-Demand pricing
            on_demand_terms = item.get('terms', {}).get('OnDemand', {})
            if not on_demand_terms:
                continue
                
            try:
                # Get the first (and usually only) on-demand term
                od_term = list(on_demand_terms.values())[0]
                price_dims = od_term.get('priceDimensions', {})
                if not price_dims:
                    continue
                    
                # Get the first price dimension
                price_dim = list(price_dims.values())[0]
                hourly_price = price_dim.get('pricePerUnit', {}).get('USD', '0')
                
                # Only include if we have a valid price
                if hourly_price and float(hourly_price) > 0:
                    results.append({
                        'instanceType': instance_type,
                        'databaseEngine': attrs.get('databaseEngine', 'Unknown'),
                        'region': location,
                        'deploymentOption': attrs.get('deploymentOption', 'Single-AZ'),
                        'licenseModel': attrs.get('licenseModel', 'Unknown'),
                        'hourlyPriceUSD': float(hourly_price),
                        'sku': item.get('product', {}).get('sku')
                    })
            except (ValueError, TypeError) as e:
                # Skip entries with invalid pricing data
                continue
    
    return results

def main():
    print("Fetching RDS pricing data...")
    pricing_data = get_rds_pricing()
    
    # Remove duplicates (same instance type + engine combination)
    seen = set()
    unique_data = []
    for entry in pricing_data:
        key = f"{entry['instanceType']}_{entry['databaseEngine']}_{entry['deploymentOption']}"
        if key not in seen:
            seen.add(key)
            unique_data.append(entry)
    
    # Sort by instance type for better organization
    unique_data.sort(key=lambda x: x['instanceType'])
    
    # Write to JSON file
    output_file = 'rds_pricing.json'
    with open(output_file, 'w') as outfile:
        json.dump(unique_data, outfile, indent=2)
    
    print(f"RDS pricing data written to {output_file} ({len(unique_data)} unique entries)")
    
    # Show a few examples
    print("\nSample entries:")
    for i, entry in enumerate(unique_data[:10]):
        print(f"{i+1}. {entry['instanceType']} ({entry['databaseEngine']}) - ${entry['hourlyPriceUSD']}/hour")

if __name__ == '__main__':
    main()

# import boto3
# import json

# pricing = boto3.client(
#     'pricing',
#     region_name='us-east-1',
#     aws_access_key_id=ACCESS_KEY,
#     aws_secret_access_key=SECRET_KEY
# )

# def get_ec2_pricing():
#     paginator = pricing.get_paginator('get_products')
#     results = []
#     filters = [
#         {'Type': 'TERM_MATCH', 'Field': 'serviceCode', 'Value': 'AmazonEC2'}
#     ]
    
#     page_count = 0
#     max_pages = 5  # Reduced for debugging
    
#     for page in paginator.paginate(ServiceCode='AmazonEC2', Filters=filters, MaxResults=100):
#         page_count += 1
#         print(f"Processing page {page_count} with {len(page['PriceList'])} items...")
        
#         if page_count > max_pages:
#             print(f"Reached maximum page limit ({max_pages}), stopping...")
#             break
        
#         for price_item in page['PriceList']:
#             item = json.loads(price_item)
            
#             # Extract product attributes
#             attrs = item.get('product', {}).get('attributes', {})
#             instance_type = attrs.get('instanceType')
#             location = attrs.get('location', '')
            
#             # Debug: Print all available attribute keys for first few items
#             if len(results) < 3:
#                 print(f"Available attributes: {list(attrs.keys())}")
#                 print(f"instanceType: {instance_type}, location: {location}")
#                 print(f"Sample attrs: {dict(list(attrs.items())[:10])}")  # First 10 attributes
#                 print("---")
            
#             # Much more relaxed filtering - just check for instance type and US East location
#             if not instance_type or 'US East' not in location:
#                 continue
            
#             # Extract On-Demand pricing
#             on_demand_terms = item.get('terms', {}).get('OnDemand', {})
#             if not on_demand_terms:
#                 continue
                
#             try:
#                 # Get the first (and usually only) on-demand term
#                 od_term = list(on_demand_terms.values())[0]
#                 price_dims = od_term.get('priceDimensions', {})
#                 if not price_dims:
#                     continue
                    
#                 # Get the first price dimension
#                 price_dim = list(price_dims.values())[0]
#                 hourly_price = price_dim.get('pricePerUnit', {}).get('USD', '0')
                
#                 # Only include if we have a valid price
#                 if hourly_price and float(hourly_price) > 0:
#                     results.append({
#                         'instanceType': instance_type,
#                         'vCPU': attrs.get('vcpu', 'Unknown'),
#                         'memory': attrs.get('memory', 'Unknown'),
#                         'storage': attrs.get('storage', 'EBS-only'),
#                         'networkPerformance': attrs.get('networkPerformance', 'Unknown'),
#                         'operatingSystem': attrs.get('operatingSystem', 'Linux'),
#                         'region': location,
#                         'tenancy': attrs.get('tenancy', 'Shared'),
#                         'hourlyPriceUSD': float(hourly_price),
#                         'sku': item.get('product', {}).get('sku'),
#                         'productFamily': attrs.get('productFamily', 'Unknown'),
#                         'usagetype': attrs.get('usagetype', 'Unknown')
#                     })
                    
#                     # Debug: Show first few matches
#                     if len(results) <= 5:
#                         print(f"Match found: {instance_type} - ${hourly_price}/hour - OS: {attrs.get('operatingSystem', 'Unknown')}")
                        
#             except (ValueError, TypeError) as e:
#                 continue
    
#     return results

# def main():
#     print("Fetching EC2 pricing data...")
#     pricing_data = get_ec2_pricing()
    
#     # Remove duplicates (same instance type + OS combination)
#     seen = set()
#     unique_data = []
#     for entry in pricing_data:
#         key = f"{entry['instanceType']}_{entry['operatingSystem']}"
#         if key not in seen:
#             seen.add(key)
#             unique_data.append(entry)
    
#     # Sort by instance type for better organization
#     unique_data.sort(key=lambda x: x['instanceType'])
    
#     # Write to JSON file
#     output_file = 'ec2_pricing.json'
#     with open(output_file, 'w') as outfile:
#         json.dump(unique_data, outfile, indent=2)
    
#     print(f"EC2 pricing data written to {output_file} ({len(unique_data)} unique entries)")
    
#     # Show a few examples
#     print("\nSample entries:")
#     for i, entry in enumerate(unique_data[:10]):
#         print(f"{i+1}. {entry['instanceType']} ({entry['operatingSystem']}) - {entry['vCPU']} vCPU, {entry['memory']} - ${entry['hourlyPriceUSD']}/hour")

# if __name__ == '__main__':
#     main()
