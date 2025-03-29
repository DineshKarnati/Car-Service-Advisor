import streamlit as st
import time
from app import rag_advisor  # Importing the RAG advisor function

# Set up Streamlit page config
st.set_page_config(page_title="AI RAG Advisor", layout="wide", page_icon="🤖")

# Custom CSS for better chat styling
st.markdown("""
    <style>
        body {
            background-image: url('https://source.unsplash.com/1600x900/?technology,ai');
            background-size: cover;
            background-attachment: fixed;
        }
        .stTextInput > div > div > input {
            font-size: 16px;
        }
        .bot-message {
            background-color: #2C3E50;
            color: white;
            padding: 10px;
            border-radius: 10px;
            max-width: 80%;
        }
        .user-message {
            background-color: #3498DB;
            color: white;
            padding: 10px;
            border-radius: 10px;
            max-width: 80%;
            align-self: flex-end;
        }
        .chat-container {
            display: flex;
            flex-direction: column;
        }
    </style>
""", unsafe_allow_html=True)

# Sidebar with chatbot info
st.sidebar.image("https://source.unsplash.com/400x300/?robot,chatbot", use_container_width=True)
st.sidebar.title("🤖 AI RAG Advisor")
st.sidebar.markdown("Welcome to the AI-powered RAG Advisor Chatbot. Have a conversation with me about your issues and get expert insights!")

# Initialize session state variables
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Display Chat History
st.markdown("<h1 style='text-align: center; color: white;'>AI-Powered RAG Advisor Chat</h1>", unsafe_allow_html=True)

# Chat container
chat_container = st.container()

# Display chat history
with chat_container:
    for chat in st.session_state.chat_history:
        if chat["role"] == "user":
            st.markdown(f"<div class='user-message'>👤 You: {chat['content']}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='bot-message'>🤖 Advisor: {chat['content']}</div>", unsafe_allow_html=True)

# Dynamic Key Fix - Prevents previous input from persisting
unique_input_key = f"user_input_{len(st.session_state.chat_history)}"

# User Input (ensuring it resets)
user_query = st.text_input("💬 Type your question below and continue the conversation:", key=unique_input_key)

# Button Row (Submit & Clear Chat)
col1, col2 = st.columns([5, 1])

with col1:
    submit_button = st.button("🚀 Send Query")

with col2:
    clear_button = st.button("🗑️ Clear Chat")

# Clear Chat History
if clear_button:
    st.session_state.chat_history = []
    st.rerun()  #FIXED: Use `st.rerun()` instead of `st.experimental_rerun()`

# Handle Chatbot Interaction
if submit_button and user_query.strip():
    # Store user message in history
    st.session_state.chat_history.append({"role": "user", "content": user_query})

    # Simulate "thinking" effect
    with st.spinner("🤖 Thinking..."):
        time.sleep(2)  # Simulating a slight delay
        bot_response = rag_advisor(user_query)

    # Store bot response in chat history
    st.session_state.chat_history.append({"role": "assistant", "content": bot_response})

    # Refresh UI to clear input field
    st.rerun()  #FIXED: Use `st.rerun()`
