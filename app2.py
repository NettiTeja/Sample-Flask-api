
import requests, base64

invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
stream = False


headers = {
  "Authorization": "Bearer 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",
  "Accept": "text/event-stream" if stream else "application/json"
}
def chat(user_input):
    
    payload = {
    "model": "meta/llama-4-maverick-17b-128e-instruct",
    "messages": [{"role":"user","content":user_input}],
    "max_tokens": 512,
    "temperature": 1.00,
    "top_p": 1.00,
    "frequency_penalty": 0.00,
    "presence_penalty": 0.00,
    "stream": stream
    }

    response = requests.post(invoke_url, headers=headers, json=payload)

    if stream:
        for line in response.iter_lines():
            if line:
                print(line.decode("utf-8"))
    else:
        # print(response.json())
        print("response_content: ",response.json()["choices"][0]["message"]["content"])

user_input=input("ask your question.enter 'quit' for exit chat: ")
while(user_input!='quit'):
    chat(user_input)
    user_input=input("ask your question.enter 'quit' for exit chat: ")
