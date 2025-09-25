from datetime import datetime
import json
from elasticsearch import Elasticsearch

# Replace with your actual credentials
ELASTICSEARCH_URL = "https://my-elasticsearch-project-ce364c.es.us-central1.gcp.elastic.cloud:443"
API_KEY = "R1drNlhwa0JhOVpXdDFuWVhocWU6LU9Ra0JHMnFraVpHUlVtbjJSRkE1UQ=="

# Create the Elasticsearch client instance
client = Elasticsearch(
    ELASTICSEARCH_URL,
    api_key=API_KEY
)

file_path = "elastic-start-local/vending.json"

try:
    # Open the file in read mode ('r')
    with open(file_path, 'r') as file:
        # Load the JSON data from the file into a Python variable
        vending_machines_data = json.load(file)
        
    # Now, vending_machines_data is a Python list containing your JSON objects
    # You can print it to verify
    # print(vending_machines_data)

except FileNotFoundError:
    print(f"Error: The file '{file_path}' was not found.")
except json.JSONDecodeError:
    print(f"Error: The file '{file_path}' is not a valid JSON file.")
except Exception as e:
    print(f"An unexpected error occurred: {e}")

index_name = "vending-machines"

try:
    for doc in vending_machines_data:
        # We use the 'machine_id' as the document ID for each document
        response = client.index(
            index=index_name,
            id=doc['machine_id'],
            document=doc
        )
        print(f"Indexed document {response['_id']} with result: {response['result']}")

    print(f"\nSuccessfully indexed {len(vending_machines_data)} documents into the '{index_name}' index.")

except Exception as e:
    print(f"An error occurred during indexing: {e}")

print("\n=== Starting search ===")

try:
    # Define the search query
    # This example will search for all documents where the "payment_methods" field contains "Cash"
    search_query = {
        "query": {
            "match": {
                "payment_methods": "Cash"
            }
        }
    }

    # Execute the search
    search_response = client.search(
        index=index_name,
        body=search_query
    )

    # Print the search results
    print(f"Found {search_response['hits']['total']['value']} matching documents.")
    for hit in search_response['hits']['hits']:
        print(f"--- ID: {hit['_id']}, Store Name: {hit['_source']['store_name']}, City: {hit['_source']['city']}")

except Exception as e:
    print(f"An error occurred during the search: {e}")

print("\n=== Search complete ===")