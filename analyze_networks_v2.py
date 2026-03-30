import csv
import os
from collections import defaultdict

def read_csv_with_encoding(filepath):
    """Try to read a CSV with different encodings."""
    encodings = ['utf-8', 'utf-16', 'latin-1']
    for enc in encodings:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                # Try to read a line to see if it works
                line = f.readline()
                # Reset file pointer
                f.seek(0)
                reader = csv.DictReader(f)
                # If we get here, the encoding worked
                return reader
        except UnicodeDecodeError:
            continue
        except Exception as e:
            # Other exceptions (like missing headers) we break and report
            raise e
    # If none worked, raise an error
    raise ValueError(f"Could not decode {filepath} with tried encodings")

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
                    reader = read_csv_with_encoding(filepath)
                    for row in reader:
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