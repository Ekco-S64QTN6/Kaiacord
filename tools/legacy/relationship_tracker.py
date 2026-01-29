"""
relationship_tracker.py - Tracks and visualizes relationship development over time
"""

import json
import os
from datetime import datetime
from typing import Dict, List
import matplotlib.pyplot as plt
import numpy as np

def analyze_relationship_evolution(user_folder: str):
    """Analyze how the relationship with a user has evolved over time"""
    
    analysis_path = os.path.join(user_folder, "profile_analysis.json")
    if not os.path.exists(analysis_path):
        print(f"No analysis data found for {user_folder}")
        return
    
    with open(analysis_path, "r") as f:
        data = json.load(f)
    
    # Track metrics over time (simplified - in reality would need time-series data)
    metrics = {
        "Trust Growth": data.get("relationship", {}).get("trust_growth", 0),
        "Interaction Frequency": data.get("stats", {}).get("total_interactions", 0),
        "Personal Questions": 1 if data.get("relationship", {}).get("asks_personal_questions") else 0,
        "Technical Depth": data.get("style", {}).get("metrics", {}).get("technical_depth", 0)
    }
    
    # Generate simple visualization
    fig, ax = plt.subplots(figsize=(10, 6))
    
    labels = list(metrics.keys())
    values = list(metrics.values())
    
    bars = ax.bar(labels, values)
    
    # Color code by metric type
    colors = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D']
    for bar, color in zip(bars, colors):
        bar.set_color(color)
    
    user_name = os.path.basename(user_folder).rsplit("_", 1)[0].replace("_", " ")
    ax.set_title(f"Relationship Metrics: {user_name}", fontsize=14, fontweight='bold')
    ax.set_ylabel("Score", fontsize=12)
    
    plt.tight_layout()
    
    # Save the visualization
    viz_path = os.path.join(user_folder, "relationship_evolution.png")
    plt.savefig(viz_path, dpi=150)
    plt.close()
    
    print(f"✓ Relationship visualization saved: {viz_path}")
    
    # Generate relationship insights
    insights = generate_relationship_insights(data)
    insights_path = os.path.join(user_folder, "relationship_insights.md")
    
    with open(insights_path, "w") as f:
        f.write(insights)
    
    print(f"✓ Relationship insights saved: {insights_path}")

def generate_relationship_insights(data: Dict) -> str:
    """Generate actionable insights for relationship building"""
    
    relationship = data.get("relationship", {})
    style = data.get("style", {})
    topics = data.get("topics", {}) # Note: in generate_user_profiles.py it's saved as 'topics'
    
    stage = relationship.get("stage", "unknown")
    trust = relationship.get("trust_level", "unknown")
    
    insights = f"""# RELATIONSHIP INSIGHTS
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## CURRENT STATUS
- **Stage**: {stage.capitalize()}
- **Trust Level**: {trust.capitalize()}
- **Familiarity**: {relationship.get('familiarity', 'professional').capitalize()}

## RECOMMENDED ACTIONS

### For Kaia:
"""
    
    if stage == "early":
        insights += """1. **Build Foundation**: Focus on reliability and competence
2. **Ask Open Questions**: Encourage sharing about interests
3. **Be Consistent**: Establish predictable response patterns
4. **Share Small Personal Touches**: Mention coffee, cat, etc. to humanize
"""
    elif stage == "developing":
        insights += """1. **Deepen Topics**: Follow up on mentioned interests
2. **Remember Details**: Reference past conversations
3. **Offer Proactive Help**: Anticipate needs based on patterns
4. **Share Vulnerabilities**: Admit when things are complex or uncertain
"""
    elif stage == "established":
        insights += """1. **Maintain Depth**: Continue meaningful conversations
2. **Challenge Gently**: Push thinking on familiar topics
3. **Collaborate**: Suggest joint "projects" or thought experiments
4. **Be Fully Present**: No need to hold back technical depth
"""
    
    # Add style-specific tips
    style_labels = style.get("style_labels", [])
    if "technical" in style_labels:
        insights += """
### Technical Communication:
- Use precise terminology
- Include code examples when relevant
- Don't oversimplify unless asked
"""
    
    if "humorous" in style_labels:
        insights += """
### Humor Notes:
- Light sarcasm is acceptable
- Tech jokes land well
- Don't force humor if serious topic
"""
    
    # Interest-based connection points
    primary_interests = topics.get("primary_interests", [])
    if primary_interests:
        insights += f"""
### Connection Opportunities:
The user is interested in: {', '.join(primary_interests[:3])}
- Ask about progress on mentioned projects
- Share relevant tech news or articles
- Connect their interests to current conversations
"""
    
    return insights

def main():
    """Analyze all user relationships"""
    log_dir = "knowledge_base/user_logs"
    if not os.path.exists(log_dir):
        print(f"Log directory {log_dir} not found")
        return
        
    user_folders = [f.path for f in os.scandir(log_dir) if f.is_dir()]
    
    print(f"Analyzing relationships for {len(user_folders)} users...")
    
    for folder in user_folders:
        user_name = os.path.basename(folder).rsplit("_", 1)[0].replace("_", " ")
        print(f"\nAnalyzing: {user_name}")
        analyze_relationship_evolution(folder)

if __name__ == "__main__":
    main()
