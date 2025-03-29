from constants import SCHEMA_DESCRIPTION
import openai
import os
import numpy as np
from dotenv import load_dotenv
load_dotenv() # Load environment variables
from database import driver
openai.api_key = os.getenv("OPENAI_API_KEY")
embedding_model = os.getenv("EMBEDDING_MODEL")
get_latest_bot_content = lambda chat_history: next((msg["content"] for msg in reversed(chat_history) if msg["role"] == "assistant"), "")

# Chat history memory
vChatHistory = []  # Stores past interactions

def get_openai_response(prompt):
    structured_output =''
    try:
        response = openai.chat.completions.create(
                model="gpt-4o", 
                messages=[{"role": "user", "content": prompt}]
            )

        structured_output = response.choices[0].message.content
    except Exception as ex: print(f"Exception in getting open ai response {ex}")
    return structured_output

# Generate OpenAI Embeddings
def get_openai_embedding(text):
    """Generate an embedding vector for a given text."""
    try:
        response = openai.embeddings.create(input=text, model=embedding_model)
        return response.data[0].embedding
    except Exception as e:
        print(f"Embedding error: {e}")
        return None

def rephrase(user_query,chat_history):
    result = ''
    prompt = f"""Based on the provided conversation history, the following user query needs to be modified to capture all key details and named entities if they are referenced using pronouns or third person references. 
                  The primary goal is to ensure the query is clear, concise, and contains all necessary named entities for accurate and precise similarity search. 
                  If the query already contains all required details, return it as-is. Do not return any explanations or duplicate previously asked questions. If modification is needed, ensure the query remains true to the original intent and meaning.
                  Chat History: {chat_history}
                  Query to modify:{user_query}
                  
                  Warning: Do not explain anything"""
    result = get_openai_response(prompt)
    return result

# Fetch Related Nodes Based on Problem or Child Node
def get_related_nodes(node_name, node_type):
    """Finds related nodes based on whether the node is a Problem or a child node."""
    try:
        with driver.session(database=os.getenv('DATABASE')) as session:
            if node_type == "Problem":
                # If node is a Problem, find all child nodes
                query = """
                MATCH (p:Problem {name: $node_name})-[:HAS_PROCEDURES|:HAS_SUBCOMPONENT|:HAS_TESTPROCEDURES
         |:HAS_SUBPROBLEM|:HAS_ADDITIONALINFO|:HAS_SYMPTOM
         |:HAS_SUSPECTAREA|:HAS_BASICINFO]->(child)
                RETURN labels(child) AS child_type, child.name AS child_name
                """
                result = session.run(query, node_name=node_name)
                related_nodes = [{"node_type": record["child_type"][0], "name": record["child_name"]} for record in result]

            else:
                # If node is a child, find the parent Problem node and its children
                query = """
                MATCH (problem:Problem)-[:HAS_PROCEDURES|:HAS_SUBCOMPONENT|:HAS_TESTPROCEDURES
         |:HAS_SUBPROBLEM|:HAS_ADDITIONALINFO|:HAS_SYMPTOM
         |:HAS_SUSPECTAREA|:HAS_BASICINFO]->(child {name: $node_name})
                WITH problem
                MATCH (problem)-[:HAS_PROCEDURES|:HAS_SUBCOMPONENT|:HAS_TESTPROCEDURES
         |:HAS_SUBPROBLEM|:HAS_ADDITIONALINFO|:HAS_SYMPTOM
         |:HAS_SUSPECTAREA|:HAS_BASICINFO]->(related_child)
                RETURN labels(problem) AS problem_type, problem.name AS problem_name, 
                       labels(related_child) AS child_type, related_child.name AS child_name
                """
                result = session.run(query, node_name=node_name)
                related_nodes = []
                problem_name = None

                for record in result:
                    if problem_name is None:
                        problem_name = record["problem_name"]  # Get parent problem name
                    related_nodes.append({"node_type": record["child_type"][0], "name": record["child_name"]})

                if problem_name:
                    print(f"Identified Parent Problem: {problem_name}")

            return related_nodes
    except Exception as e:
        print(f"Error retrieving related nodes: {e}")
        return []
    
def process_top_nodes(results):
    """Processes the top 3 retrieved nodes and finds their related nodes accordingly."""
    content = []
    for idx, node in enumerate(results):
        # print(f"\n🔹 Top {idx+1} Retrieved Node: {node['node_type']} - {node['name']}")
        related_nodes = get_related_nodes(node["name"], node["node_type"][0])

        if related_nodes:
            print(f"➡️ Related Nodes for {node['name']}:")
            for rel in related_nodes:
                content.append(f"   🔸 {rel['node_type']}: {rel['name']}")
        else:
            print("   ⚠️ No related nodes found.")
    return content

# Perform Vector Search in Neo4j
def vector_search(query_vector, node_label, top_k=3, threshold=0.7):
    """Retrieve top-k similar nodes using vector search."""
    if query_vector is None:
        return []
    
    try:
        query_vector = np.array(query_vector, dtype=np.float32).tolist()
        index_name = f'vectorIndex_{node_label}'
        cypher_query = """
        CALL db.index.vector.queryNodes(
            $index_name,
            $top_k,
            $query_vector
        ) YIELD node, score
        WHERE score >= $threshold
        RETURN labels(node) AS node_type, node.name AS name, score
        """
        with driver.session(database=os.getenv('DATABASE')) as session:
            results = session.run(
                cypher_query,
                index_name=index_name,
                query_vector=query_vector,
                top_k=top_k,
                threshold=threshold
            )
            return [record.data() for record in results]
    except Exception as e:
        print(f"Vector search error: {e}")
        return []


# Retrieve Data from Neo4j Based on User Query
def retrieve_data(user_query):
    """Retrieve top 3 most relevant nodes for the given query."""
    query_vector = get_openai_embedding(user_query)
    all_matches = []

    for node_label in SCHEMA_DESCRIPTION.keys():
        matches = vector_search(query_vector, node_label)
        all_matches.extend(matches)

    # Deduplicate and sort by highest score
    unique_results = []
    seen = set()
    for match in sorted(all_matches, key=lambda x: x['score'], reverse=True):
        identifier = match.get('name')
        if identifier not in seen:
            seen.add(identifier)
            unique_results.append(match)

    return unique_results[:3]  # Return top 3 results

def final_call(user_query,content):
    result = ''
    
    prompt = f"""
Act as an **automobile service agent** and answer the user's query based on structured automotive data.

### **Context Information**
You have access to a **knowledge graph** containing details about:
- **Problems** (e.g., engine overheating, AC not cooling)
- **Symptoms** (e.g., unusual noises, high temperature warnings)
- **Procedures** (e.g., troubleshooting, installation steps)
- **Test Procedures** (e.g., voltage checks, radiator pressure tests)
- **Suspect Areas** (e.g., battery, compressor, cooling system)
- **Additional Information** (e.g., car specifications, manufacturer details)
- **Subcomponents** (e.g., alternator, fuel pump)

### **Instructions**
- Use the following retrieved content to generate an accurate response:
  
  **Content:**  
  {content}

- Answer the user query with **precise and relevant information only**:
  
  **User Query:**
  {user_query}

- **Strict Constraints:**
  - Only use the provided context.
  - **Do NOT generate an answer** if no relevant information is found.
  - Ensure responses are clear, concise, and helpful to the user.
"""

    result = get_openai_response(prompt)
    return result

# RAG-Based Advisor Logic
def rag_advisor(user_query):
    """Processes the query, maintains chat history, and retrieves structured responses."""
    global vChatHistory

    # Store query in chat history
    vChatHistory.append({"role": "user", "content": user_query})

    retrieved_results = retrieve_data(user_query)
    content = process_top_nodes(retrieved_results)
    #rephrase
    if vChatHistory:
        user_query = rephrase(user_query, get_latest_bot_content(vChatHistory))
    response = final_call(user_query,content)
    vChatHistory.append({"role": "assistant", "content": f"user_query:{user_query},response:{response}"})

    return response
