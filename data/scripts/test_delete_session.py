import requests

BASE_URL = "http://localhost:8001"

def test_delete_session():
    print("1. Logging in as dysp1...")
    res = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "dysp1", "password": "demo1234"})
    assert res.status_code == 200
    token = res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    print("2. Fetching cases...")
    res = requests.get(f"{BASE_URL}/api/cases", headers=headers)
    assert res.status_code == 200
    cases = res.json().get("cases", [])
    if not cases:
        print("  Creating a test case...")
        res = requests.post(f"{BASE_URL}/api/cases", json={"title": "Test Case"}, headers=headers)
        case_id = res.json()["case_id"]
    else:
        case_id = cases[0]["case_id"]
        
    print(f"3. Creating a new test session in case {case_id}...")
    res = requests.post(f"{BASE_URL}/api/cases/{case_id}/sessions", headers=headers)
    assert res.status_code == 200
    session_id = res.json()["session_id"]
    print(f"  Created test session: {session_id}")
    
    print(f"4. Testing DELETE /api/sessions/{session_id}...")
    del_res = requests.delete(f"{BASE_URL}/api/sessions/{session_id}", headers=headers)
    print(f"  DELETE response code: {del_res.status_code}, body: {del_res.json()}")
    assert del_res.status_code == 200
    print("✅ Chat Session Delete test PASSED successfully!")

if __name__ == "__main__":
    test_delete_session()
