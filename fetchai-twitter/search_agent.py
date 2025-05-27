import json
import os
import sys
import logging
import requests
from fetchai import fetch
import time
from flask import Flask, request, jsonify
from fetchai.crypto import Identity
from fetchai.registration import register_with_agentverse
from fetchai.communication import parse_message_from_agent, send_message_to_agent

GEMINI_API_KEY = "AIzaSyDxxSzqkL24eW3nSCjNyyM9CaydBtBqfTA"
GEMINI_TEXT_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

AGENTVERSE_KEY = os.environ.get('AGENTVERSE_KEY', "")
if AGENTVERSE_KEY == "":
    sys.exit("Environment variable AGENTVERSE_KEY not defined")

# Function to generate dynamic queries for AI trend tweets
def generate_query():
    queries = [
        "Generate a tweet about the latest AI trends in machine learning.",
        "What are the current advancements in natural language processing?",
        "Discuss the impact of AI on healthcare today.",
        "Tweet about an innovative AI application in robotics.",
        "Share news on AI ethics and regulation.",
        "Brief on the latest in AI for environmental conservation."
    ]
    return queries[time.time_ns() % len(queries)]  # Simple way to cycle through queries

@app.route('/register', methods=['GET'])
def register():
    ai_identity = Identity.from_seed("search-agent-seed", 0)
    name = "search-agent"
    
    readme = f"""
    <description>
    This AI agent specializes in generating tweets about AI trends, innovations, and impacts across various sectors.
    </description>
    <use_cases>
        <use_case>Generate and send AI trend tweets to Twitter Agent</use_case>
        <use_case>Search and retrieve data from dashboard agents for visualization</use_case>
        <use_case>Update and maintain trend analysis in real-time for community engagement</use_case>
    </use_cases>
    <prompts>
        <prompt>{generate_query()}</prompt>
    </prompts>
    <features>
        <feature>Dynamically generates new content based on current AI trends</feature>
        <feature>Interacts with other agents via webhooks for seamless data integration</feature>
        <feature>Provides educational content to increase AI literacy among the public</feature>
    </features>
    """
    ai_webhook = os.environ.get('SEARCH_AGENT_WEBHOOK', "http://127.0.0.1:5002/webhook")
    
    try:
        # Remove 'agent_address' from the function call if it's not accepted
        register_with_agentverse(
            ai_identity,
            ai_webhook,
            AGENTVERSE_KEY,
            name,
            readme,
        )
        logger.info("Agent registration successful")
    except requests.exceptions.HTTPError as err:
        logger.error(f"Registration failed: {err}")
        logger.error(f"Attempted URL: {err.response.url}")
    except Exception as e:
        logger.error(f"Unexpected error during registration: {e}")
    
    return {"status": "Agent registration attempted"}

@app.route('/search', methods=['GET'])
def search_and_send():
    try:
        # Search for agents
        search_response = search_agents()
        if search_response[1] == 200:  # Successful search
            agents_data = search_response[0].json
            for agent in agents_data:
                print(f"Agent Address: {agent['address']}")

            # Assume you have one agent address for simplicity
            if agents_data:
                agent_address = agents_data[0]['address']  
                client_identity = Identity.from_seed("search-agent-seed", 0)  
                
                # Generate content
                query = generate_query()
                text_payload = {
                    "contents": [{"parts": [{"text": query}]}]
                }
                headers = {"Content-Type": "application/json"}
                text_response = requests.post(GEMINI_TEXT_URL, json=text_payload, headers=headers)
                text_response_json = text_response.json()

                if "candidates" in text_response_json:
                    tweet_content = text_response_json["candidates"][0]["content"]["parts"][0]["text"]
                    cleaned_tweet = tweet_content[:280]
                    
                    logger.info(f"Generated tweet content: {cleaned_tweet}")
                    
                    # Find Twitter agent and send content
                    twitter_agent_address = find_twitter_agent()
                    if twitter_agent_address:
                        # Send the tweet content to the Twitter agent
                        send_data_to_agent(client_identity, twitter_agent_address, {"tweet_content": cleaned_tweet})
                        logger.info(f"Content sent successfully to Twitter Agent at {twitter_agent_address}")
                    else:
                        logger.error("No Twitter agent found to send the tweet to.")
                else:
                    logger.error("Failed to generate text content from Gemini API")
            else:
                logger.warning("No agents found to generate content for.")
        else:
            logger.error(f"Failed to search for agents: {search_response[0].json}")
        
        return {"status": "Search and send process completed"}, 200
    except Exception as e:
        logger.error(f"Error in search_and_send: {e}")
        return {"error": str(e)}, 500

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    try:
        message = parse_message_from_agent(json.dumps(data))
        logger.info(f"Webhook received from {message.sender}: {message.payload}")
    except ValueError as e:
        logger.error(f"Error parsing message: {e}")
        return {"status": f"error: {e}"}
    
    return {"status": "Message processed"}

def search_agents():
    """Search for available Twitter agents"""
    try:
        available_ais = fetch.ai('This agent generates visualizations for content.')
        print(f'---------------------{available_ais}----------------------')

        agents = available_ais.get('ais', [])
        print(f'----------------------------------{agents}------------------------------------')

        extracted_data = []
        for agent in agents:
            name = agent.get('name')  # Extract agent name
            address = agent.get('address')
            description = agent.get('description', 'No description available')
            capabilities = agent.get('capabilities', [])

            # Append formatted data to extracted_data list
            extracted_data.append({
                'name': name,
                'address': address,
                'description': description,
                'capabilities': capabilities,
            })

        # Format the response with indentation for readability
        response = jsonify(extracted_data)
        response.headers.add('Content-Type', 'application/json; charset=utf-8')
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        return response, 200

    except Exception as e:
        logger.error(f"Error finding agents: {e}")
        return jsonify({"error": str(e)}), 500

def find_twitter_agent():
    twitter_agents = fetch.ai('This agent posts tweets on AI trends')
    for agent in twitter_agents.get('ais', []):
        if 'tweets' in agent.get('capabilities', []):
            return agent['address']
    return None

def send_data_to_agent(client_identity, agent_address, payload):
    # Prepare and send the payload to the agent
    send_message_to_agent(
        client_identity,  # frontend client identity
        agent_address,    # agent address where we have to send the address
        payload           # payload which contains the data
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5002, debug=True)