import csv
import os
from collections import defaultdict

def find_network_companies():
    # Dictionary to store companies and the cities they appear in
    company_cities = defaultdict(set)
    
    # Base directory
    base_dir = "cities"
    
    # Walk through all directories
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if file.endswith('.csv'):
                filepath = os.path.join(root, file)
                try:
                    # Try different encodings
                    encodings = ['utf-8', 'utf-16', 'latin-1']
                    file_content = None
                    
                    for enc in encodings:
                        try:
                            with open(filepath, 'r', encoding=enc) as f:
                                file_content = f.read()
                            break  # Success, break out of encoding loop
                        except UnicodeDecodeError:
                            continue
                    
                    if file_content is None:
                        print(f"Could not decode {filepath} with tried encodings")
                        continue
                    
                    # Parse CSV content
                    lines = file_content.strip().split('\n')
                    if not lines:
                        continue
                        
                    # Get headers from first line
                    headers = lines[0].split(',')
                    # Clean headers (remove quotes, spaces)
                    headers = [h.strip().strip('"') for h in headers]
                    
                    # Process data rows
                    for line in lines[1:]:
                        if not line.strip():
                            continue
                        values = line.split(',')
                        # Handle quoted fields with commas inside - simple approach
                        # For now, we'll assume no commas inside quoted fields for simplicity
                        # A proper CSV parser would be better, but this should work for our data
                        
                        # Pad or truncate values to match headers
                        if len(values) < len(headers):
                            values.extend([''] * (len(headers) - len(values)))
                        elif len(values) > len(headers):
                            values = values[:len(headers)]
                            
                        row = dict(zip(headers, values))
                        
                        company_name = row.get('name', '').strip()
                        city = row.get('city', '').strip()
                        
                        if company_name and city:
                            company_cities[company_name].add(city)
                            
                except Exception as e:
                    print(f"Error reading {filepath}: {e}")
    
    # Find companies that appear in 2 or more cities
    network_companies = {name: cities for name, cities in company_cities.items() if len(cities) >= 2}
    
    # Sort by number of cities (descending)
    sorted_networks = sorted(network_companies.items(), key=lambda x: len(x[1]), reverse=True)
    
    print("Крупные сетевые компании, работающие в разных городах:")
    print("=" * 60)
    
    for company, cities in sorted_networks:
        print(f"\n{company}")
        print(f"  Города ({len(cities)}): {', '.join(sorted(cities))}")
    
    print("\n" + "=" * 60)
    print(f"Всего найдено сетевых компаний: {len(sorted_networks)}")
    
    return sorted_networks

if __name__ == "__main__":
    find_network_companies()