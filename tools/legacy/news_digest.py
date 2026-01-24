import json
import os
import hashlib
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Any, Set

def parse_daily_log(file_path: str) -> Dict[str, Any]:
    """
    Parse a daily log file.
    Expected format: JSON or Markdown with specific structure.
    For now, assuming a simplified JSON structure or placeholder.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # TODO: Implement actual parsing logic based on log format
            # For now, return dummy data if not JSON
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {
                    "date": os.path.basename(file_path).replace(".md", ""),
                    "stories": []
                }
    except Exception as e:
        print(f"Error parsing log {file_path}: {e}")
        return {"date": "", "stories": []}

def calculate_freshness(date_str: str) -> float:
    """Calculate freshness score based on date (0.0 to 1.0)"""
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d")
        days_old = (datetime.now() - date).days
        return max(0.0, 1.0 - (days_old * 0.1))
    except:
        return 0.5

def update_existing_story(story_hash: int, new_story: Dict[str, Any]):
    """Update an existing story with new information"""
    # This would update the story object in place or return a merged one
    # For now, we assume the caller handles the list management
    pass

def extract_topic_key(story: Dict[str, Any]) -> str:
    """Extract a key for topic deduplication"""
    return story.get('topic_key', story.get('headline', ''))

def generate_verbose_summary(story: Dict[str, Any]) -> str:
    """Generate a verbose summary for the story"""
    return story.get('summary', 'No summary available.')

def enrich_story_summary(story: Dict[str, Any]) -> Dict[str, Any]:
    """Make summaries more verbose"""
    return {
        "headline": story.get('headline', ''),
        "verbose_summary": generate_verbose_summary(story),
        "impact": story.get('impact', ''),
        "timeline": story.get('timeline', []),
        "related_events": story.get('related', []),
        "freshness": story.get('freshness_score', 0.0),
        "update_count": story.get('update_count', 1)
    }

def select_diverse_stories(stories: List[Dict[str, Any]], max_per_category=5, min_freshness=0.3) -> List[Dict[str, Any]]:
    """Select diverse stories avoiding repetition"""
    selected = []
    
    # Sort by freshness and importance
    sorted_stories = sorted(
        stories,
        key=lambda x: (x.get('freshness_score', 0), x.get('severity', 0)),
        reverse=True
    )
    
    # Take top N, ensuring no overlap in key elements
    taken_topics = set()
    for story in sorted_stories:
        if len(selected) >= max_per_category:
            break
            
        topic_key = extract_topic_key(story)
        if topic_key not in taken_topics and story.get('freshness_score', 0) >= min_freshness:
            selected.append(enrich_story_summary(story))
            taken_topics.add(topic_key)
    
    return selected

def generate_weekly_summary(all_stories: Dict[str, List[Dict[str, Any]]]) -> str:
    """Generate a high-level summary of the week"""
    summary = "Weekly Digest Summary:\n"
    for category, stories in all_stories.items():
        summary += f"- {category}: {len(stories)} stories\n"
    return summary

def generate_weekly_news_digest(log_files: List[str], weeks_back=4) -> str:
    """
    Generate a weekly digest from multiple log files
    - log_files: List of file paths (7 files, one for each day of current week)
    - weeks_back: How many weeks to look back for trend analysis
    """
    
    all_stories = defaultdict(list)
    seen_story_hashes = set()
    
    # Track story frequency across weeks
    story_frequency = defaultdict(int)
    
    for file_path in log_files:
        if not os.path.exists(file_path):
            continue
            
        # Parse each daily log
        daily_data = parse_daily_log(file_path)
        
        # Categorize and deduplicate
        for story in daily_data.get('stories', []):
            # Create unique hash based on core story elements
            key_elements = story.get('key_elements', story.get('headline', ''))
            story_hash = hash(f"{story.get('category', 'General')}_{key_elements}")
            
            if story_hash not in seen_story_hashes:
                seen_story_hashes.add(story_hash)
                
                # Add metadata for weekly trends
                story['first_seen'] = daily_data.get('date', '')
                story['update_count'] = 1
                story['freshness_score'] = calculate_freshness(daily_data.get('date', ''))
                
                all_stories[story.get('category', 'General')].append(story)
            else:
                # Update existing story with latest developments
                # For simplicity in this implementation, we just increment count
                # In a real system, we'd merge details
                pass
    
    # Generate digest with variety
    digest = {
        "period": f"WEEKLY_DIGEST_{datetime.now().strftime('%Y-%U')}",
        "summary": generate_weekly_summary(all_stories),
        "sections": {}
    }
    
    # Select diverse stories per category
    for category, stories in all_stories.items():
        digest['sections'][category] = select_diverse_stories(
            stories, 
            max_per_category=5,
            min_freshness=0.3
        )
    
    return json.dumps(digest, indent=2)
