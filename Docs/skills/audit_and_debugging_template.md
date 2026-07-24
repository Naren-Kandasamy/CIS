# Debugging & Codebase Audit Report Template

**Date:** YYYY-MM-DD  
**Project/System:** [Project Name]  
**Author(s):** [Your Name / Team]  
**Status:** [RESOLVED / UNRESOLVED / MITIGATED]  
**Environment:** [e.g., Production, Staging, Local, Catalyst, AWS]

---

## 1. Executive Summary
*Provide a 2-3 sentence high-level summary of the issue, the impact on the system, and the ultimate resolution. This allows future readers to quickly grasp what this document covers without reading the technical deep-dive.*

---

## 2. System State & Environment Context
*Document the state of the system when the debugging session began.*
* **Architecture/Component Involved:** [e.g., Backend API, Serverless Function, Database]
* **Relevant URLs/Endpoints:** [List any failing endpoints]
* **Recent Changes:** [List any recent deployments, code changes, or infrastructure updates that might have triggered this]

---

## 3. Symptom Logging & Initial Hypotheses
*What exactly was broken? Record the raw errors here.*
* **Reported Issue:** [e.g., "Frontend hangs in QUEUED state", "500 Internal Server Error on checkout"]
* **Raw Error Logs/Tracebacks:**
  ```text
  [Paste relevant raw stack traces, error codes, or console output here]
  ```
* **Initial Hypotheses:** 
  1. *Hypothesis A...*
  2. *Hypothesis B...*

---

## 4. Step-by-Step Diagnostic Trail
*Document the exact steps taken to isolate the problem. This is critical for understanding the "Why" and avoiding repetitive debugging in the future.*

### **Test 1: [What did you test?]**
* **Action:** [e.g., Pinged the /health endpoint directly via cURL]
* **Expected Outcome:** [e.g., HTTP 200 OK]
* **Actual Outcome:** [e.g., HTTP 405 Method Not Allowed]
* **Conclusion/Adjustment:** [e.g., Health probes are failing, indicating an ingress routing issue, not a code issue.]

### **Test 2: [Next logical test]**
* **Action:** 
* **Expected Outcome:** 
* **Actual Outcome:** 
* **Conclusion/Adjustment:** 

---

## 5. Root Cause Analysis
*Explain exactly what caused the failure. Go beyond the surface-level error message to explain the architectural or logical flaw.*

* **The Core Issue:** [e.g., The Python `neo4j` driver maintains background tasks tied to the `asyncio` event loop. When the serverless container destroyed the loop, the background tasks crashed upon the next invocation.]
* **Why it wasn't caught earlier:** [e.g., This only happens across multiple invocations in a serverless environment; local testing maintains a persistent event loop.]

---

## 6. Remediation Steps & Code Changes
*What exact changes were made to fix the issue? Include file paths and conceptual diffs.*

* **File:** `path/to/file.py`
  * **Change:** [e.g., Stripped out global driver caching and implemented explicit `await driver.close()` inside a `try...finally` block.]
* **Configuration / Infrastructure Changes:**
  * [e.g., Added `ZC_PROJECT_ID` to the Catalyst UI Development environment.]
  * [e.g., Removed `"env_variables": {}` from `catalyst-config.json` to prevent deployment overrides.]

---

## 7. Verification & Final Validation
*How do you know it's permanently fixed?*
* **Validation Test Performed:** [e.g., Executed the benchmark query "Are there any robbery gangs..." through the live UI.]
* **Result:** [e.g., Full graph retrieval succeeded, UI rendered citations properly.]

---

## 8. Prevention Mechanisms (Lessons Learned)
*What can be done to ensure this class of bugs never happens again?*
* [e.g., Add automated CI/CD checks for environment variable presence.]
* [e.g., Standardize all serverless database connections to avoid global state caching.]
