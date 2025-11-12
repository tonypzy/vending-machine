import google.generativeai as genai
genai.configure(api_key="AIzaSyCWQaE8mBjc8x93wbXlgK1-pi4yJ3MzbnM")

for m in genai.list_models():
    print(m.name)
