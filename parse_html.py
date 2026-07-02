from bs4 import BeautifulSoup

with open('/home/nkandasamy/Desktop/CIS/Docs/QuickML LLM Usage Transition Guide - Zoho Corp.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')
    text = soup.get_text(separator='\n', strip=True)
    print(text[:2000]) # First 2000 characters
    print("\n...\n")
    # Search for anything related to API keys, tokens, QuickML Endpoints, or 'zoho-inputstream'
    for tag in soup.find_all(['h1', 'h2', 'h3', 'p', 'pre', 'code']):
        if 'token' in tag.text.lower() or 'auth' in tag.text.lower() or 'model' in tag.text.lower() or 'api' in tag.text.lower():
            print(f"[{tag.name}] {tag.text}")
