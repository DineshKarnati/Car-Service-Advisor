from constants import NODE_SIMILAR_TAGS
from database import execute_query
from neo4j import GraphDatabase
import xml.etree.ElementTree as ET
import os
import re
from dotenv import load_dotenv
load_dotenv() # Load environment variables


def get_standardized_label(tag):
    """Maps a given tag to its standardized node label using node_similar_tags."""
    for standard_label, synonyms in NODE_SIMILAR_TAGS.items():
        if tag in synonyms:
            return standard_label
    return "AdditionalInfo" # If no match, return original tag in lowercase



def clean_xml(xml_content):
    """Cleans the XML content by removing invalid characters, fixing malformed XML,
       escaping reserved characters, and ensuring a valid root element."""
    try:
        # Remove non-printable ASCII control characters except tab, newline, and carriage return
        xml_content = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F]', '', xml_content)

        # Fix malformed ampersands that are not part of valid XML entities
        xml_content = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;)', '&amp;', xml_content)

        # Remove Byte Order Mark (BOM) if present at the start
        if xml_content.startswith("\ufeff"):
            xml_content = xml_content.lstrip("\ufeff")

        # Fix improperly formatted inline tags like "<15–1>"
        xml_content = re.sub(r'<(\d+–\d+)>', r'(\1)', xml_content)

        # Ensure the entire XML content is wrapped inside a valid root tag
        xml_content = f"<root>{xml_content}</root>"

        return xml_content

    except Exception as e:
        print(f"Error cleaning XML content: {e}")
        return xml_content


def extract_full_text(element):
    """Extracts text from an XML element, including all nested children, appending tag names to the text."""

    texts = []

    if element.text and element.text.strip():
        texts.append(f"{element.tag}: {element.text.strip()}")  # Append tag name with text

    for child in element:
        child_text = extract_full_text(child)  # Recursively get child text
        if child_text:
            texts.append(child_text)  # Append child text if not empty

    return " | ".join(filter(None, texts))  # Join non-empty text with separator for clarity


def parse_and_insert_data(xml_content: str, component_name: str):
    """Parses the XML file and inserts structured data into Neo4j with correct relationships."""
    try:
        xml_content = clean_xml(xml_content)
        root = ET.fromstring(xml_content)

        # Ensure Model and Manufacturer exist
        execute_query("MERGE (pg:ProductGroup {name: 'automobile'})")
        execute_query("MERGE (man:Manufacturer {name: 'toyota motor corporation'})")
        execute_query("MERGE (m:Model {name: 'yaris', series: 'ncp91, 93 series'})")

        execute_query("""
            MATCH (pg:ProductGroup {name: 'automobile'})
            MATCH (m:Model {name: 'yaris'})
            MERGE (pg)-[:HAS_MODEL]->(m)
        """)

        execute_query("""
            MATCH (m:Model {name: 'yaris'})
            MATCH (man:Manufacturer {name: 'toyota motor corporation'})
            MERGE (m)-[:MANUFACTURED_BY]->(man)
        """)

        execute_query("MERGE (c:Component {name: $name})", {"name": component_name.lower()})
        execute_query("""
            MATCH (m:Model {name: 'yaris'})
            MATCH (c:Component {name: $name})
            MERGE (m)-[:HAS_COMPONENT]->(c)
        """, {"name": component_name.lower()})

        problems = root.findall("problem")

        first_problem_index, last_problem_index = None, None
        for i, elem in enumerate(root):
            if elem.tag == "problem":
                if first_problem_index is None:
                    first_problem_index = i
                last_problem_index = i

        # Before first problem -> Link all parent tags to the component
        if first_problem_index is not None:
            for i in range(first_problem_index):
                element = root[i]
                standardized_label = get_standardized_label(element.tag)
                text_value = extract_full_text(element)

                execute_query(f"MERGE (n:{standardized_label} {{name: $name}})", {"name": text_value})
                execute_query(f"""
                    MATCH (c:Component {{name: $component_name}})
                    MATCH (n:{standardized_label} {{name: $name}})
                    MERGE (c)-[:HAS_{standardized_label.upper()}]->(n)
                """, {"component_name": component_name.lower(), "name": text_value})

        # If more than 3 problems, create parent problem node
        if len(problems) > 3:
            parent_problem_name = f"{component_name.lower()}_problems"
            execute_query("MERGE (p:Problem {name: $name})", {"name": parent_problem_name})

        for problem_tag in problems:
            problem_name = problem_tag.text.strip().lower()

            # Ensure the problem node exists
            execute_query("MERGE (p:Problem {name: $name})", {"name": problem_name})

            if len(problems) > 3:
                execute_query("""
                    MATCH (p1:Problem {name: $parent_name})
                    MATCH (p2:Problem {name: $problem_name})
                    MERGE (p1)-[:HAS_SUBPROBLEM]->(p2)
                """, {"parent_name": parent_problem_name, "problem_name": problem_name})

            current_index = list(root).index(problem_tag)

            for i in range(current_index + 1, len(root)):
                element = root[i]
                if element.tag == "problem":  # Stop when next problem starts
                    break

                standardized_label = get_standardized_label(element.tag)
                text_value = extract_full_text(element)

                # Instead of using APOC, handle the logic with standard Cypher queries
                execute_query(f"""
                    MATCH (p:Problem {{name: $problem_name}})
                    OPTIONAL MATCH (p)-[:HAS_{standardized_label.upper()}]->(n:{standardized_label} {{name: $name}})
                    WITH p, n, $name AS name, "{standardized_label}" AS label

                    // Create new node if it does not exist
                    FOREACH (_ IN CASE WHEN n IS NULL THEN [1] ELSE [] END |
                        CREATE (newNode:{standardized_label} {{name: name}})
                        MERGE (p)-[:HAS_{standardized_label.upper()}]->(newNode)
                    )

                    // Update existing node if it exists
                    FOREACH (_ IN CASE WHEN n IS NOT NULL THEN [1] ELSE [] END |
                        SET n.name = n.name + " | " + name
                    )
                """, {"problem_name": problem_name, "name": text_value})

        # After last problem -> Link all tags back to component
        if last_problem_index is not None:
            for i in range(last_problem_index + 1, len(root)):
                element = root[i]
                standardized_label = get_standardized_label(element.tag)
                text_value = extract_full_text(element)

                execute_query(f"MERGE (n:{standardized_label} {{name: $name}})", {"name": text_value})
                execute_query(f"""
                    MATCH (c:Component {{name: $component_name}})
                    MATCH (n:{standardized_label} {{name: $name}})
                    MERGE (c)-[:HAS_{standardized_label.upper()}]->(n)
                """, {"component_name": component_name.lower(), "name": text_value})

    except Exception as e:
        print(f"Error processing data: {e}")



if __name__ == "__main__":
    folder_path= os.getenv('DATA_FOLDER_PATH')

    if os.path.exists(folder_path):
        for file_name in os.listdir(folder_path):
            with open(os.path.join(folder_path, file_name), "r", encoding="utf-8") as file:
                parse_and_insert_data(file.read(), file_name.replace("_extracted.tsx", "").replace(".tsx", "").lower())
