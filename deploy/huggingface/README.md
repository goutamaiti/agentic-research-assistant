---
title: Agentic Research Assistant
emoji: 📄
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: Evidence-linked analysis and Q&A for one research paper
---

# Agentic Research Assistant

Upload one academic PDF. The app extracts structured research knowledge, links every
claim to quoted passages with page numbers, checks each claim against its sources, and
answers questions about the paper with page citations.

Source code, local one-click setup and documentation:
https://github.com/goutamaiti/agentic-research-assistant

**Note:** on free Space hardware, uploaded papers and analyses are lost whenever the
Space restarts or goes to sleep. Do not upload confidential papers; the text is sent to
Google Gemini for analysis.
