# Lenny-Growth-Assistant-Chatbot
I built a local RAG-based assistant that lets users ask questions and retrieve relevant evidence from the transcript corpus

Lenny Growth Assistant is a local AI-powered RAG application that helps users answer product, growth, startup, and leadership questions using Lenny’s Podcast transcripts.

It combines FAISS semantic search, BM25 keyword search, RRF, and Cross-Encoder reranking to retrieve relevant evidence, then uses local Ollama LLM inference to generate grounded answers with source citations. It also supports HTML artifact generation, PostgreSQL conversation persistence, and developer diagnostics for retrieval and performance monitoring.

Steps to Execute
================

1. Clone the Project
--------------------

Open Command Prompt and run:

git clone https://github.com/GiridharanMS08/Lenny-Growth-Assistant-Chatbot.git
cd Lenny-Growth-Assistant-Chatbot


2. Check Ollama
---------------

Open Command Prompt and run:

ollama list

If the required model is not installed, run:

ollama pull qwen3:1.7b


3. Check PostgreSQL
-------------------

Make sure PostgreSQL is installed and running.

Create a database with the STRICT database name:

lenny

Open PostgreSQL (psql) and run:

CREATE DATABASE lenny;


4. Configure the .env Files---------------------------

The project contains two .env.example files.

Configure both:  .env.example and  backend\.env.example
Open each file using Notepad or any text editor.

Find:
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/lenny
Replace YOUR_PASSWORD with your actual PostgreSQL password.

Example:
DATABASE_URL=postgresql+psycopg://postgres:Abc123@localhost:5432/lenny
IMPORTANT:
- The database name must remain: lenny
- Replace only YOUR_PASSWORD with your PostgreSQL password.


5. Run the Application
----------------------
Double-click:
start.bat
The application setup and startup process will begin.


6. Select the Ollama Model
--------------------------
Select the preferred model:

A = qwen3:1.7b
B = qwen3:4b
C = qwen3:8b

7. Wait for Backend Startup
---------------------------
The Backend Terminal will open.
Wait until the model weights are loaded and the terminal displays:
Application startup complete

8. Open the Frontend
--------------------
Navigate to the Frontend Terminal.
Ctrl + Click the displayed frontend URL.
Alternatively, copy the URL and paste it into your browser.

9. Use the Application
----------------------
Ask a question in the Lenny Growth Assistant.
The application will process the query and return:
- Answer
- Retrieved sources
- Relevant evidence

10. Stop the Application
------------------------
To stop the application, go to the running terminal window and press:
Ctrl + C
This will stop the running application.



