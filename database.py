from neo4j import GraphDatabase
from dotenv import load_dotenv
import os
load_dotenv() # Load environment variables

# Neo4j Driver
driver = GraphDatabase.driver(os.getenv('NEO_URI'), auth=(os.getenv('NEO_USERNAME'), os.getenv('NEO4J_PASSWORD')))

def execute_query(query, parameters=None):
    """Executes a Cypher query on Neo4j with error handling."""
    try:
        with driver.session(database=os.getenv('DATABASE')) as session:
            session.run(query, parameters or {})
    except Exception as e:
        print(f"Error executing query: {query}\nError: {e}")

if __name__ == "__main__":
    try:
        # Example: Running a test query
        print("Neo4j connection established. Ready to execute queries.")
    finally:
        driver.close()
        