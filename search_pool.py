import os
import ast

def search_files(directory):
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    if "ThreadPoolExecutor" in content:
                        print(f"Found in {path}")
                except Exception:
                    pass

search_files('/home/nkandasamy/Desktop/CIS/backend/.packages')
