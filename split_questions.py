import json
import csv
import re
import os

# --- KEYWORD LISTS ---

HM_KEYWORDS = [
    "career goals", "career objective", "future plans", "five years", "5 years",
    "ten years", "10 years", "leadership", "leadership style", "team management",
    "people management", "stakeholder", "stakeholders", "cross functional",
    "cross-functional", "conflict resolution", "difficult teammate", "difficult coworker",
    "motivation", "motivated", "motivating team", "ownership", "initiative",
    "decision making", "decision-making", "prioritization", "prioritize", "tradeoff",
    "trade-off", "business impact", "business value", "customer impact", "customer obsession",
    "strategy", "strategic thinking", "vision", "mission", "organizational goals",
    "company goals", "culture fit", "culture add", "work style", "communication",
    "collaboration", "teamwork", "mentor", "mentoring", "coaching", "feedback",
    "performance review", "promotion", "career growth", "strengths", "weaknesses",
    "greatest strength", "greatest weakness", "challenge", "biggest challenge",
    "failure", "mistake", "lesson learned", "achievement", "accomplishment",
    "proud project", "success story", "behavioral", "behavioral question",
    "tell me about a time", "situation task action result", "star method", "ambiguity",
    "risk management", "change management", "remote work", "hybrid work",
    "work life balance", "why this company", "why our company",
    "why do you want to work here", "why should we hire you", "salary expectation",
    "compensation", "notice period", "relocation", "lead a project", "managed a team",
    "project ownership", "influence without authority", "executive communication",
    "business problem", "customer problem", "product vision", "roadmap",
    "long term goal", "short term goal", "managerial experience", "management experience",
    "organizational impact"
]

RECRUITER_KEYWORDS = [
    "introduce yourself", "tell me about yourself", "background", "resume", "cv",
    "profile", "education", "degree", "college", "university", "graduation", "btech",
    "mtech", "experience", "work experience", "internship", "intern", "current company",
    "previous company", "employment history", "job history", "availability",
    "available to join", "joining date", "joining time", "notice period",
    "location preference", "preferred location", "work authorization", "visa",
    "citizenship", "salary", "salary expectation", "expected ctc", "current ctc",
    "compensation", "benefits", "offer", "offers in hand", "other offers", "relocation",
    "remote", "onsite", "hybrid", "employment gap", "career gap", "gap year",
    "career break", "reason for leaving", "why leaving", "why switch", "job search",
    "interview process", "hiring process", "references", "reference check", "linkedin",
    "portfolio", "github", "certification", "certifications", "notice", "joining",
    "availability to start", "eligible", "eligibility", "employment type", "full time",
    "part time", "contract", "contractor", "freelance", "shift timing",
    "willing to travel", "background verification", "background check",
    "expected package", "preferred role", "preferred domain", "screening",
    "screening call", "hr round", "recruitment", "recruiter", "talent acquisition",
    "human resources", "candidate profile"
]

TECH_KEYWORDS = [
    "concept", "theory", "explain", "what is", "difference between", "compare",
    "advantages", "disadvantages", "pros and cons", "architecture", "design pattern",
    "best practice", "internals", "working principle", "how does it work",
    "under the hood", "database", "sql", "nosql", "mongodb", "mysql", "postgresql",
    "oracle", "index", "indexing", "normalization", "denormalization", "acid",
    "cap theorem", "transaction", "locking", "deadlock", "operating system", "os",
    "process", "thread", "multithreading", "concurrency", "parallelism",
    "synchronization", "mutex", "semaphore", "memory management", "virtual memory",
    "paging", "cache", "cpu scheduling", "networking", "tcp", "udp", "http", "https",
    "dns", "load balancer", "firewall", "rest api", "graphql", "microservices",
    "monolith", "docker", "kubernetes", "cloud", "aws", "azure", "gcp",
    "authentication", "authorization", "oauth", "jwt", "encryption", "hashing",
    "security", "oop", "object oriented programming", "inheritance", "polymorphism",
    "encapsulation", "abstraction", "solid principles", "dependency injection",
    "framework", "library", "compiler", "interpreter", "garbage collection", "runtime",
    "java", "python", "javascript", "react", "angular", "nodejs", "spring boot",
    "django", "flask", "machine learning", "deep learning", "neural network", "cnn",
    "rnn", "transformer", "llm", "artificial intelligence", "data structure",
    "algorithm", "time complexity", "space complexity", "big o", "big-o"
]

CODING_KEYWORDS = [
    "code", "coding", "program", "write a program", "implement", "implementation",
    "function", "method", "algorithm", "leetcode", "hackerrank", "codeforces",
    "coding challenge", "coding round", "solve", "solution", "brute force",
    "optimized", "time complexity", "space complexity", "edge case", "test case",
    "debug", "debugging", "bug", "fix bug", "binary search", "two pointers",
    "sliding window", "recursion", "backtracking", "dynamic programming", "dp",
    "greedy", "graph", "tree", "binary tree", "bst", "linked list", "stack", "queue",
    "heap", "priority queue", "trie", "union find", "disjoint set", "dfs", "bfs",
    "topological sort", "shortest path", "dijkstra", "bellman ford", "floyd warshall",
    "minimum spanning tree", "kruskal", "prim", "sorting", "merge sort", "quick sort",
    "heap sort", "counting sort", "radix sort", "hash map", "hash table", "set",
    "array", "matrix", "string", "substring", "palindrome", "anagram", "permutation",
    "combination", "coding exercise", "online assessment", "oa",
    "competitive programming", "pseudo code", "pseudocode", "write code",
    "complete code", "find output", "dry run", "trace execution"
]

SYSTEM_DESIGN_KEYWORDS = [
    "system design", "design a system", "design twitter", "design instagram",
    "design youtube", "design whatsapp", "design uber", "design netflix",
    "design chat system", "design url shortener", "design tinyurl", "design facebook",
    "design search engine", "high level design", "hld", "low level design", "lld",
    "architecture design", "distributed system", "distributed systems", "scalability",
    "scalable", "scale to millions", "scale to billions", "availability",
    "high availability", "fault tolerance", "fault-tolerant", "reliability",
    "redundancy", "replication", "sharding", "partitioning", "load balancing",
    "load balancer", "caching", "cache invalidation", "cdn", "message queue", "kafka",
    "rabbitmq", "pub sub", "pub-sub", "event driven", "event-driven", "event sourcing",
    "stream processing", "data pipeline", "throughput", "latency", "qps", "rps",
    "capacity estimation", "traffic estimation", "database design", "schema design",
    "microservice design", "service discovery", "api gateway", "reverse proxy",
    "consistency", "eventual consistency", "strong consistency", "cap theorem",
    "distributed cache", "redis", "memcached", "rate limiter", "rate limiting",
    "websocket", "long polling", "polling", "real time system", "real-time system",
    "leader election", "consensus", "raft", "paxos", "monitoring", "logging",
    "observability", "alerting", "disaster recovery", "backup strategy",
    "storage design", "object storage", "blob storage", "geo replication",
    "multi region", "multi-region", "multi tenant", "multi-tenant", "data partitioning",
    "horizontal scaling", "vertical scaling", "service architecture", "queue design",
    "notification system", "recommendation system", "news feed", "feed generation"
]

FALLBACK_KEYWORDS = [
    "interview", "question", "answer", "candidate", "job", "position", "role",
    "experience", "project", "technology", "software engineer", "developer", "engineer"
]

# Buckets for the output
buckets = {
    "system_design": [],
    "coding": [],
    "technical": [],
    "hiring_manager": [],
    "recruiter": [],
    "unclassified": []
}

def clean_html(raw_html):
    """Remove HTML tags from text."""
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', str(raw_html))
    return cleantext.strip()

def classify_question(q_text):
    """Classify the question based on priority order."""
    lower_q = q_text.lower()
    
    # 1. System Design
    if any(kw in lower_q for kw in SYSTEM_DESIGN_KEYWORDS):
        return "system_design"
    # 2. Coding
    if any(kw in lower_q for kw in CODING_KEYWORDS):
        return "coding"
    # 3. Technical
    if any(kw in lower_q for kw in TECH_KEYWORDS):
        return "technical"
    # 4. Hiring Manager
    if any(kw in lower_q for kw in HM_KEYWORDS):
        return "hiring_manager"
    # 5. Recruiter
    if any(kw in lower_q for kw in RECRUITER_KEYWORDS):
        return "recruiter"
        
    return "unclassified"

def process_file(json_file_path):
    print(f"Reading {json_file_path}...")
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for row in data:
        raw_text = row.get("q_a_text", "")
        if not raw_text or str(raw_text).strip() == "NO_QUESTIONS_FOUND":
            continue
            
        # Remove HTML
        clean_text = clean_html(raw_text)
        
        # Split by newlines first
        lines = clean_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # If it has the pipe format, e.g., "1.0 | interviewer | Question text?"
            if '|' in line:
                parts = line.split('|')
                question_part = parts[-1].strip()
            else:
                question_part = line
                
            # Now, if this part contains multiple questions separated by '?'
            if '?' in question_part:
                # Split by '?' but keep the '?'
                fragments = [frag.strip() + '?' for frag in question_part.split('?') if frag.strip()]
                # If the last fragment didn't originally end with '?', the split logic 
                # might append a '?' erroneously to a statement. Let's handle it safely.
                if not question_part.endswith('?'):
                    # The very last fragment was a statement, not a question.
                    # We can remove the artificially added '?'
                    if fragments:
                        fragments[-1] = fragments[-1][:-1].strip()
            else:
                fragments = [question_part]
                
            # Process and classify each fragment
            for frag in fragments:
                if len(frag.split()) < 4:
                    # Skip extremely short fragments like "Right?"
                    continue
                    
                bucket = classify_question(frag)
                buckets[bucket].append(frag)

    # Write to CSVs
    def write_csv(filename, bucket_key):
        items = buckets[bucket_key]
        if not items:
            return
            
        with open(filename, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['question_text'])
            for item in items:
                writer.writerow([item])
        print(f"Created {filename} with {len(items)} questions.")

    write_csv('hiring manager.csv', 'hiring_manager')
    write_csv('recruiter.csv', 'recruiter')
    write_csv('technical questions.csv', 'technical')
    write_csv('coding questions.csv', 'coding')
    write_csv('system design questions.csv', 'system_design')
    write_csv('unclassified.csv', 'unclassified')

if __name__ == "__main__":
    process_file('questions_dump.json')
