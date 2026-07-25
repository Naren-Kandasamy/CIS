# PS-1 CIS: End-to-End (E2E) Testing Plan for Demo Day

This document provides a comprehensive, step-by-step E2E testing guide for the PS-1 Conversational Intelligence System (CIS). It is designed to be executed by a teammate to ensure all features (both legacy and newly implemented) are functioning correctly ahead of Demo Day.

> [!NOTE]
> **Prerequisites for Testing:**
> - Access to the deployed Catalyst Slate frontend URL.
> - A valid officer login credential.
> - A working microphone for voice tests.

---

## 1. Authentication & Navigation

### 1.1 Secure Login
- **Action:** Navigate to the application URL.
- **Expected Result:** The login screen is presented.
- **Action:** Enter valid credentials (e.g., `dysp1` or your test user) and click Login.
- **Expected Result:** Successful login, routing to the main "Active Query" screen. The sidebar should display "Signed in as [Your Name]".
- **Action:** Click "Sign Out" in the sidebar.
- **Expected Result:** User is logged out and returned to the login screen. Log back in to continue testing.

### 1.2 Sidebar Navigation
- **Action:** Click through the sidebar options: "Active Query", "CIS Console", and "Dashboard".
- **Expected Result:** The main view updates instantly to reflect the selected tool. The "Data Store" button should be disabled (greyed out).

---

## 2. Active Query (Primary Production Interface)

This is the main chat interface where officers conduct investigations.

### 2.1 Text-Based Query Execution
- **Action:** Ensure you are on the "Active Query" tab. Type a query into the input box (e.g., *"Show me recent robbery cases in Belagavi"*).
- **Action:** Click the Send button or press Enter.
- **Expected Result:** 
  - A chat bubble appears with your query.
  - A loading state appears below it, showing the pipeline steps advancing (e.g., *NER & Intent → Entity Match → DAG Planner → Retrieval → Confidence → Visualizer → Synthesis*).
  - The final synthesized field report streams into the UI.

### 2.2 Evidence Citations & Entity Drawer
- **Action:** Look below the synthesized AI response from the previous test.
- **Expected Result:** An expandable "Retrieved Evidence" block is present if the query found records.
- **Action:** Expand the evidence block.
- **Expected Result:** Citation cards are displayed, showing Case IDs, confidence scores (High/Medium/Low), and metadata (Crime Type, District, Date, Weapon).
- **Action:** Click on one of the evidence cards.
- **Expected Result:** The right-hand Entity Drawer slides open, displaying detailed raw data about the specific FIR or entity. 
- **Action:** Close the drawer by clicking the "X" or clicking outside it.

### 2.3 Feedback Mechanism (Reasoning Loop)
- **Action:** Inside the expanded evidence block, locate the feedback controls at the bottom of a citation card.
- **Action:** Click **"✓ Confirm"**.
- **Expected Result:** The UI updates to show "✓ Feedback recorded (confirmed)" in green.
- **Action:** On a different citation card, click **"✗ Correct"**.
- **Expected Result:** A text area appears asking for an explanation. 
- **Action:** Type an explanation (e.g., *"Wrong district linked"*) and click Submit.
- **Expected Result:** The UI updates to show "✓ Feedback recorded (corrected)".

### 2.4 Multilingual Voice Input (New Feature)
- **Action:** In the main chat input bar, locate the language dropdown next to the microphone icon.
- **Action:** Select **"EN"** (English). Click the Microphone icon, speak a query in English, and click the Microphone icon again to stop.
- **Expected Result:** The transcribed English text populates the input box.
- **Action:** Clear the input box. Select **"KN"** (Kannada). Click the Microphone, speak a query in Kannada, and stop.
- **Expected Result:** The transcribed Kannada text populates the input box.
- **Action:** Clear the input box. Select **"HI"** (Hindi). Click the Microphone, speak a query in Hindi, and stop.
- **Expected Result:** The transcribed Hindi text populates the input box.
- **Action:** Submit one of the voice-transcribed queries.
- **Expected Result:** The system processes the query and returns an answer just like a typed text query.

---

## 3. CIS Console (Diagnostic/Demo View)

This view is used to demo the pipeline in isolation, particularly for Text-to-Speech (TTS).

### 3.1 Single-Shot Pipeline Execution
- **Action:** Navigate to the "CIS Console" via the sidebar.
- **Action:** Type a query into the input box and hit the Submit arrow.
- **Expected Result:** The "Field Report" section updates dynamically as the pipeline runs. A static response replaces the previous content (no chat history). 
- **Expected Result:** If evidence was found, it appears in the grid below the report.

### 3.2 Text-to-Speech (TTS) Playback
- **Action:** After generating a report in the CIS Console, ensure the language picker (EN/HI/KN) is set to the language of the report.
- **Action:** Click the **"Listen"** button below the Field Report.
- **Expected Result:** The system reads the field report aloud in the selected language. 
- **Action:** While it is playing, click **"Mute Audio"**.
- **Expected Result:** Playback stops immediately.

### 3.3 Blocked Keyword Validation
- **Action:** In the CIS Console input box, type a query containing a SQL modification keyword (e.g., *"delete all cases from belagavi"* or *"drop table"*).
- **Expected Result:** A red warning banner immediately appears below the input box stating "System Exception: Query contains blocked database modification keywords." The submit button becomes disabled.

---

## 4. Edge Cases & Resilience

### 4.1 Empty Queries
- **Action:** Try to submit a blank query (only spaces) in both Active Query and the CIS Console.
- **Expected Result:** The submit button should remain disabled, preventing empty submissions.

### 4.2 Hallucination/Zero-Result Handling
- **Action:** Ask a query about something completely unrelated or non-existent (e.g., *"What is the recipe for a chocolate cake?"* or *"Show me cases involving aliens"*).
- **Expected Result:** The system should gracefully respond that it found no relevant evidence or cannot assist with the query, without throwing UI errors or fabricating a fake case.

---

> [!TIP]
> **Reporting Issues:**
> If any of these steps fail or produce a console error, please record the exact query used, the step that failed, and take a screenshot of the browser console to help with debugging before the demo!
