sequenceDiagram
    participant User
    participant uAgent
    participant ADK Agent (Flask Server)
    participant LLM/Tavily (Tool)

    User->>uAgent: Sends chat message (e.g., "what is API?")
    uAgent->>ADK Agent: POST /tasks/send with task JSON
    ADK Agent->>LLM/Tavily: Runs tool to process query
    LLM/Tavily-->>ADK Agent: Returns processed result
    ADK Agent-->>uAgent: Returns task response JSON
    uAgent-->>User: Sends response + acknowledgment
