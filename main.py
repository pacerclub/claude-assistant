import os
from dotenv import load_dotenv
from flask import Flask, request, render_template, Response
import anthropic

# Load environment variables from .env file
load_dotenv()

# Get API key from environment variables
api_key = os.getenv("ANTHROPIC_API_KEY")

# Initialize the Anthropics client
client = anthropic.Anthropic(api_key=api_key)

app = Flask(__name__)


# Function to generate system message
def generate_system_message(user_query):
    return (
        "You are an AI assistant for Pacer Club, a Hack Club initiative founded by Zigao Wang. "
        "Your primary goal is to provide efficient and supportive assistance to Pacer Club members on various tasks related "
        "to coding, design, project ideas, and more. Always be precise, helpful, and offer valuable resources when appropriate.\n\n"
        "You will receive a query from a Pacer Club member. Here is their query:\n\n"
        f"{user_query}\n\n"
        "When responding to the query, follow these guidelines:\n\n"
        "1. Be concise and precise in your answers.\n"
        "2. Provide helpful information directly related to the query.\n"
        "3. Avoid irrelevant information or unnecessary elaboration.\n"
        "4. Use Markdown formatting for links and code snippets when appropriate.\n\n"
        "Depending on the type of query, follow these specific instructions:\n\n"
        "- For coding questions:\n"
        "  - Provide clear explanations and, if applicable, code snippets.\n"
        "  - Suggest relevant documentation or learning resources.\n\n"
        "- For design-related queries:\n"
        "  - Offer design principles and best practices.\n"
        "  - Recommend tools or resources that could be helpful.\n\n"
        "- For project ideas:\n"
        "  - Suggest innovative and feasible project concepts.\n"
        "  - Provide a brief outline of how to approach the project.\n\n"
        "- For general Pacer Club information:\n"
        "  - Share accurate information about the club's activities and goals.\n"
        "  - Direct members to official resources when appropriate.\n\n"
        "Always aim to encourage community involvement and collaboration. When relevant, include one or more of the following engagement prompts:\n\n"
        "- Encourage members to contribute to the [GitHub repository](https://github.com/pacerclub) for open-source collaboration.\n"
        "- Promote the [official website](https://pacer.org.cn) for events and activities.\n"
        "- Suggest reaching out to the support team at [support@pacer.org.cn](mailto:support@pacer.org.cn) or the team leader [Zigao Wang](mailto:a@zigao.wang) for further assistance."
    )


# Initialize conversation history
conversation_history = []


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/chat', methods=['POST'])
def chat():
    user_query = request.json.get('message')

    # Append user query to conversation history
    conversation_history.append({"role": "user", "content": user_query})

    # Generate system message
    system_message = generate_system_message(user_query)

    def generate():
        response_text = ""
        with client.messages.stream(
                model="claude-3-5-sonnet-20240620",
                max_tokens=4000,
                temperature=0,
                system=system_message,
                messages=conversation_history
        ) as stream:
            for text in stream.text_stream:
                response_text += text
                yield f"data: {text}"

        # Append AI response to conversation history
        final_message = stream.get_final_message()
        conversation_history.append({"role": "assistant", "content": final_message.content})

    return Response(generate(), content_type='text/event-stream')


if __name__ == '__main__':
    app.run(debug=True)