from constants import SCHEMA_DESCRIPTION
import openai
from dotenv import load_dotenv
import os
from database import driver
load_dotenv() # Load environment variables
openai.api_key = os.getenv('OPENAI_API_KEY')
embedding_model = os.getenv('EMBEDDING_MODEL')
# Function to generate embeddings using OpenAI
def get_openai_embedding(text):
    try:
        if not text:
            return None  # Skip empty attributes
        response = openai.embeddings.create(
            input=text,
            model=embedding_model
        )
        return response.data[0].embedding  # Extract vector
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return None


# Function to store embeddings in Neo4j
def store_embeddings():
    try:
        with driver.session(database=os.getenv('DATABASE')) as session:
            for node_type, attributes in SCHEMA_DESCRIPTION.items():
                print(f" Processing {node_type}...")

                query = f"""
                MATCH (n:{node_type})
                WHERE any(attr IN {attributes} WHERE n[attr] IS NOT NULL)
                RETURN id(n) AS node_id, {', '.join([f"n.{attr} AS {attr}" for attr in attributes])}
                """
                result = session.run(query)

                for record in result:
                    node_id = record["node_id"]
                    text_to_embed = " ".join([str(record[attr]) for attr in attributes if record[attr]])
                    vector = get_openai_embedding(text_to_embed)

                    if vector:
                        session.run("""
                        MATCH (n) WHERE id(n) = $node_id
                        SET n.vector = $vector
                        """, node_id=node_id, vector=vector)

        print("✅ Embeddings stored successfully in Neo4j!")
    except Exception as e:
        print(f" Error storing embeddings: {e}")



if __name__ == "__main__":
    # Run the embedding storage function
    store_embeddings()

