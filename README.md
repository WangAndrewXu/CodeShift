# 🚀 CodeShift

![Next.js](https://img.shields.io/badge/Next.js-Frontend-black)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-green)
![License](https://img.shields.io/badge/License-MIT-blue)

CodeShift is a full-stack web application that converts code between programming languages using rule-based logic with optional AI fallback. It supports both file upload and direct text input, making code transformation fast, flexible, and user-friendly.

---

✨ **Core capabilities**
- 🔄 Convert code between multiple languages (Python, C++, Java, JavaScript)
- 🧠 Rule-based conversion for fast and deterministic results
- 🤖 Optional AI fallback for complex cases
- 📄 Upload code files or paste code directly
- ⚡ Real-time conversion with clear UI feedback
- 🔌 Supports custom AI providers (API key + base URL + model)

---

🛠️ **Technology stack**  
Frontend built with **Next.js, React, and Tailwind CSS**  
Backend powered by **FastAPI and Python**  
AI integration supports **OpenAI-compatible APIs**

---

📂 **Project structure**

CodeShift/
├── codeshift-frontend/   # Next.js frontend
├── codeshift-backend/    # FastAPI backend
└── README.md

---

🚀 **Getting started**

Clone the repository and run both backend and frontend locally.

Backend:

cd codeshift-backend
pip install -r requirements.txt
uvicorn main:app --reload

Frontend:

cd codeshift-frontend
npm install
npm run dev

The backend runs on http://127.0.0.1:8000 and the frontend runs on http://localhost:3000.

---

🔑 **AI configuration**

When you open the app, you can configure your own AI provider by entering an API key, base URL, and model. This works with OpenAI, OpenRouter, and other OpenAI-compatible APIs.

---

🌐 **Deployment**

The recommended setup is to deploy the frontend on Vercel and the backend on Railway for a simple and scalable full-stack deployment.

---

📌 **Future improvements**
- Code error detection and automatic fix suggestions
- Multi-file project conversion
- More language support
- AI-powered optimization and refactoring

---

🤝 **Contributing**

Feel free to fork the repository and submit pull requests.

---

📄 **License**

MIT License
