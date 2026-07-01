import json
import csv
import re
import os
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# --- OVERRIDE RULES ---
SYSTEM_DESIGN_OVERRIDE = [
    "architecture",
    "architect",
    "design",
    "scalable",
    "microservice",
    "pipeline",
    "distributed",
    "multi-agent",
    "api versioning",
    "high availability",
    "fault tolerance"
]

# --- ANCHORS AND PROTOTYPES ---
CATEGORIES = {
    "recruiter": {
        "prototype": "Questions about background, experience, salary, joining date, role fit, location, resume and employment history.",
        "anchors": [
            "Tell me about yourself.",
            "Walk me through your resume.",
            "Can you summarize your professional background?",
            "What are you currently working on?",
            "Why are you looking for a new opportunity?",
            "Why are you interested in this role?",
            "What are your salary expectations?",
            "What is your current compensation?",
            "Do you have any offers in hand?",
            "When can you join?",
            "Are you open to relocation?",
            "Can you walk me through your recent experience?"
        ]
    },
    "hiring_manager": {
        "prototype": "Behavioral and leadership questions about ownership, stakeholder management, conflict resolution, prioritization, communication and business impact.",
        "anchors": [
            "Tell me about a time you handled a difficult stakeholder.",
            "How do you prioritize competing business requirements?",
            "Describe a project where things did not go as planned.",
            "How did you manage conflicting priorities across teams?",
            "Tell me about a time you influenced a decision without authority.",
            "How do you approach stakeholder management?",
            "Describe a major technical challenge you solved.",
            "How do you gather requirements for ambiguous projects?",
            "Tell me about a time you had to make a difficult tradeoff.",
            "How do you handle disagreements within a team?",
            "Describe your leadership style.",
            "Tell me about a project you are most proud of.",
            "How do you balance technical excellence with business goals?",
            "Describe a situation where you failed and what you learned."
        ]
    },
    "technical": {
        "prototype": "Questions that ask for explanations of concepts, theories, technologies, frameworks, architectures and engineering principles.",
        "anchors": [
            "What is Retrieval Augmented Generation (RAG)?",
            "What is embedding drift?",
            "Explain LoRA fine tuning.",
            "What is a vector database?",
            "How does a transformer model work?",
            "What is AB testing?",
            "What is a golden dataset?",
            "What is human in the loop (HITL)?",
            "What is the difference between REST and GraphQL?",
            "How does MLflow work?",
            "What is the CAP theorem?",
            "Explain eventual consistency.",
            "What is the difference between LangChain and LangGraph?",
            "What is the BERTScore metric?"
        ]
    },
    "coding": {
        "prototype": "Questions requiring implementation, debugging, algorithms, data structures, complexity analysis and writing code.",
        "anchors": [
            "Write a function to reverse a linked list.",
            "Implement binary search.",
            "Find the first non-repeating character in a string.",
            "Write code to detect a cycle in a linked list.",
            "Given an array, find the target element efficiently.",
            "Implement depth first search.",
            "Implement breadth first search.",
            "Find the longest substring without repeating characters.",
            "Write code to merge two sorted arrays.",
            "Debug the following Python code.",
            "What is the time complexity of this algorithm?",
            "Optimize this implementation.",
            "Return all pairs whose sum equals a target value.",
            "Implement the solution and explain your approach."
        ]
    },
    "system_design": {
        "prototype": "Questions about designing scalable systems, distributed architectures, microservices, APIs, databases, caching, reliability and large scale applications.",
        "anchors": [
            "Design a scalable URL shortening service.",
            "Design a chat application like WhatsApp.",
            "Design a recommendation system.",
            "Design a distributed logging platform.",
            "Design a large scale notification system.",
            "How would you architect a multi-agent platform?",
            "Design a hybrid retrieval pipeline end to end.",
            "Design a document processing pipeline for millions of files.",
            "How would you build a scalable RAG architecture?",
            "Design a microservices architecture for an e-commerce platform.",
            "How would you design API versioning for distributed services?",
            "Design a fault tolerant data processing system.",
            "How would you architect a healthcare authorization platform?",
            "Design a real-time analytics platform."
        ]
    }
}

SIMILARITY_THRESHOLD = 0.50

buckets = {
    "system_design": [],
    "coding": [],
    "technical": [],
    "hiring_manager": [],
    "recruiter": [],
    "unclassified": [],
    "ambiguous": []
}

def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', str(raw_html)).strip()

def build_category_embeddings(model):
    print("Encoding anchors and prototypes...")
    cat_embs = {}
    for cat_name, data in CATEGORIES.items():
        anchor_embeddings = model.encode(data["anchors"], normalize_embeddings=True)
        prototype_embedding = model.encode([data["prototype"]], normalize_embeddings=True)
        cat_embs[cat_name] = {
            "anchors": anchor_embeddings,
            "prototype": prototype_embedding[0]
        }
    return cat_embs

def get_confidence(score):
    if score > 0.75:
        return "high"
    elif score > 0.55:
        return "medium"
    return "low"

def process_file(json_file_path):
    print("Loading SentenceTransformer model...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    cat_embeddings = build_category_embeddings(model)
    cat_names = list(CATEGORIES.keys())
    
    print(f"Reading {json_file_path}...")
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    extracted_questions = []
    
    for row in data:
        raw_text = row.get("q_a_text", "")
        if not raw_text or str(raw_text).strip() == "NO_QUESTIONS_FOUND":
            continue
            
        clean_text = clean_html(raw_text)
        lines = clean_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if '|' in line:
                parts = line.split('|')
                question_part = parts[-1].strip()
            else:
                question_part = line
                
            if '?' in question_part:
                fragments = [frag.strip() + '?' for frag in question_part.split('?') if frag.strip()]
                if not question_part.endswith('?'):
                    if fragments:
                        fragments[-1] = fragments[-1][:-1].strip()
            else:
                fragments = [question_part]
                
            for frag in fragments:
                if len(frag.split()) < 4:
                    continue
                    
                # Rule-based Override
                q_lower = frag.lower()
                if any(k in q_lower for k in SYSTEM_DESIGN_OVERRIDE):
                    buckets["system_design"].append([frag, "system_design", 1.0, "high_override"])
                    continue
                    
                extracted_questions.append(frag)

    print(f"Extracted {len(extracted_questions)} non-override questions. Encoding and classifying...")
    
    batch_size = 256
    
    for i in range(0, len(extracted_questions), batch_size):
        batch = extracted_questions[i:i+batch_size]
        # Normalize the batch embeddings
        q_embs = model.encode(batch, normalize_embeddings=True)
        
        for j, question in enumerate(batch):
            q_emb = q_embs[j]
            
            cat_scores = []
            
            for cat_name in cat_names:
                anchors_emb = cat_embeddings[cat_name]["anchors"]
                proto_emb = cat_embeddings[cat_name]["prototype"]
                
                # Because vectors are normalized, dot product = cosine similarity
                anchor_sims = np.dot(anchors_emb, q_emb)
                max_anchor_sim = np.max(anchor_sims)
                
                proto_sim = np.dot(proto_emb, q_emb)
                
                final_score = (0.8 * max_anchor_sim) + (0.2 * proto_sim)
                cat_scores.append((float(final_score), cat_name))
                
            # Sort scores descending to find best and second best
            cat_scores.sort(key=lambda x: x[0], reverse=True)
            best_score, best_cat = cat_scores[0]
            second_best_score, _ = cat_scores[1]
                    
            if best_score < SIMILARITY_THRESHOLD:
                buckets["unclassified"].append([question, "unclassified", round(best_score, 4), get_confidence(best_score)])
            elif (best_score - second_best_score) < 0.05:
                # Catch edge cases where it's a tight race between two categories
                buckets["ambiguous"].append([question, "ambiguous", round(best_score, 4), "ambiguous"])
            else:
                buckets[best_cat].append([question, best_cat, round(best_score, 4), get_confidence(best_score)])

    def write_csv(filename, bucket_key):
        items = buckets[bucket_key]
        if not items:
            return
            
        with open(filename, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['question_text', 'category', 'score', 'confidence'])
            for item in items:
                writer.writerow(item)
        print(f"Created {filename} with {len(items)} questions.")

    write_csv('hiring manager.csv', 'hiring_manager')
    write_csv('recruiter.csv', 'recruiter')
    write_csv('technical questions.csv', 'technical')
    write_csv('coding questions.csv', 'coding')
    write_csv('system design questions.csv', 'system_design')
    write_csv('unclassified.csv', 'unclassified')
    write_csv('ambiguous.csv', 'ambiguous')
    
    # Optional: Write a master CSV with everything
    all_items = []
    for bucket_key in buckets:
        all_items.extend(buckets[bucket_key])
        
    if all_items:
        with open('classified_master_list.csv', 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['question_text', 'category', 'score', 'confidence'])
            for item in all_items:
                writer.writerow(item)
        print(f"Created classified_master_list.csv with all {len(all_items)} questions.")
        
    print("Done!")

if __name__ == "__main__":
    process_file('questions_dump.json')
