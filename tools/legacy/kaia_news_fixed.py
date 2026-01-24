import random
from datetime import datetime, timedelta

def get_diverse_news_topics():
    """Return diverse news categories beyond just CVEs"""
    return {
        "technology": {
            "weight": 0.25,
            "topics": [
                "AI breakthroughs", "Quantum computing", "Space exploration",
                "Consumer electronics", "Software updates", "Startup funding",
                "Gaming news", "Social media trends", "Chip manufacturing",
                "Renewable energy tech", "Biotech advances", "Robotics"
            ]
        },
        "politics": {
            "weight": 0.20,
            "topics": [
                "Elections", "Policy changes", "International relations",
                "Economic reforms", "Legislation", "Diplomatic meetings",
                "Political scandals", "Public protests", "Government spending",
                "Trade agreements", "Military developments", "Environmental policy"
            ]
        },
        "business": {
            "weight": 0.15,
            "topics": [
                "Stock market", "Mergers & acquisitions", "CEO changes",
                "Economic indicators", "Corporate earnings", "Market trends",
                "Cryptocurrency", "Real estate", "Consumer spending",
                "Supply chain issues", "Labor market", "Inflation data"
            ]
        },
        "security": {
            "weight": 0.15,
            "topics": [
                "Data breaches", "Ransomware attacks", "Vulnerability disclosures",
                "State-sponsored hacking", "Privacy regulations", "Cyber warfare",
                "Identity theft", "Phishing campaigns", "Supply chain attacks",
                "IoT security", "Cloud security", "Zero-day exploits"
            ]
        },
        "culture": {
            "weight": 0.10,
            "topics": [
                "Film & TV", "Music releases", "Celebrity news",
                "Art exhibitions", "Book releases", "Theater openings",
                "Gaming culture", "Internet memes", "Streaming services",
                "Fashion trends", "Food & dining", "Travel destinations"
            ]
        },
        "science": {
            "weight": 0.10,
            "topics": [
                "Medical breakthroughs", "Climate research", "Archaeology finds",
                "Physics discoveries", "Chemistry innovations", "Biology research",
                "Astronomy observations", "Environmental studies", "Psychology findings",
                "Mathematics proofs", "Engineering feats", "Oceanography discoveries"
            ]
        },
        "sports": {
            "weight": 0.05,
            "topics": [
                "Game results", "Player transfers", "Championship events",
                "Team standings", "Injury reports", "Coach changes",
                "Draft picks", "Record breaks", "Tournament schedules",
                "Olympic preparations", "Sports business", "Fan events"
            ]
        }
    }

def generate_news_summary(category=None):
    """Generate a more diverse news summary"""
    topics = get_diverse_news_topics()
    
    if not category or category not in topics:
        # Pick a random category weighted by importance
        weights = [topics[cat]["weight"] for cat in topics]
        categories = list(topics.keys())
        category = random.choices(categories, weights=weights, k=1)[0]
    
    # Pick a random topic from the category
    topic = random.choice(topics[category]["topics"])
    
    # Generate a more natural sounding summary
    templates = [
        f"On the {topic.lower()} front, {random.choice(['things are getting interesting', 'developments are moving fast', 'there have been some major shifts'])}. "
        f"{random.choice(['Sources indicate', 'Reports suggest', 'Industry insiders say'])} "
        f"{random.choice(['a significant announcement is expected soon', 'new regulations are being drafted', 'market forces are driving change'])}. "
        f"It's {random.choice(['definitely worth watching', 'something to keep an eye on', 'going to have ripple effects'])}.",
        
        f"Regarding {topic.lower()}, {random.choice(['the landscape is evolving', 'recent events have reshaped things', 'there\'s been notable progress'])}. "
        f"{random.choice(['Analysts are predicting', 'Experts are warning', 'Observers are noting'])} "
        f"{random.choice(['a paradigm shift in the making', 'unprecedented growth opportunities', 'potential regulatory challenges ahead'])}. "
        f"This could {random.choice(['change everything', 'open new doors', 'create interesting dynamics'])}.",
        
        f"Talk about {topic.lower()} - {random.choice(['it\'s been a busy week', 'developments are accelerating', 'the situation is fluid'])}. "
        f"{random.choice(['Key players are', 'Major organizations are', 'Governments are'])} "
        f"{random.choice(['rethinking their approach', 'doubling down on investments', 'forming new alliances'])}. "
        f"{random.choice(['Stay tuned', 'Watch this space', 'More to come'])}."
    ]
    
    return {
        "category": category,
        "topic": topic,
        "summary": random.choice(templates),
        "timestamp": datetime.now().isoformat()
    }

def get_todays_news(count=5):
    """Get today's diverse news headlines"""
    news_items = []
    
    for _ in range(count):
        news_items.append(generate_news_summary())
    
    return news_items
