import os
import re
import tempfile
import json
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, redirect, url_for
import openai

# Load environment variables
load_dotenv()

app = Flask(__name__)
# Add this after the line "app = Flask(__name__)"
@app.template_filter('fromjson')
def fromjson(value):
    return json.loads(value)

# OpenAI API key from environment variable
openai.api_key = os.getenv("OPENAI_API_KEY")

# Predefined categories for strengths and weaknesses
PREDEFINED_STRENGTHS = [
    "Rapport building and relationship skills",
    "Active listening and empathy",
    "Effective questioning techniques",
    "Clear communication and presentation",
    "Closing and follow-up skills"
]

PREDEFINED_WEAKNESSES = [
    "Lack of personalization/research",
    "Insufficient value demonstration",
    "Poor objection handling",
    "Communication issues (clarity, filler words)",
    "Call structure and organization problems"
]

# Predefined categories for objections
PREDEFINED_OBJECTIONS = [
    "Price/budget concerns",
    "Need more time to decide",
    "Need to consult others",
    "Already using a competitor",
    "No perceived need/value",
    "Past negative experience",
    "Implementation concerns",
    "Contract/terms issues"
]

# Database setup
def get_db_connection():
    """Create a connection to the SQLite database"""
    conn = sqlite3.connect('sales_calls.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database with necessary tables"""
    conn = get_db_connection()
    conn.execute('''
    CREATE TABLE IF NOT EXISTS calls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        transcript TEXT NOT NULL,
        feedback TEXT NOT NULL,
        strengths TEXT,
        weaknesses TEXT,
        objections TEXT,
        overall_rating INTEGER,
        date_analyzed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()

# Initialize database when the app starts
init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/history')
def history():
    conn = get_db_connection()
    calls = conn.execute('SELECT * FROM calls ORDER BY date_analyzed DESC').fetchall()
    conn.close()
    return render_template('history.html', calls=calls)

def find_best_category_match(point, categories):
    """Find the best matching category for a given point using simple keyword matching"""
    point_lower = point.lower()
    
    # Simple keyword matching
    keywords = {
        "Rapport building and relationship skills": ["rapport", "relationship", "trust", "connection", "friendly", "dialogue"],
        "Active listening and empathy": ["listen", "empathy", "understanding", "attentive", "customer's needs", "demonstrated empathy"],
        "Effective questioning techniques": ["question", "probe", "inquiry", "discovery", "open-ended"],
        "Clear communication and presentation": ["communication", "articulate", "clear", "concise", "presentation"],
        "Closing and follow-up skills": ["close", "closing", "commitment", "follow-up", "next steps", "secure", "meeting", "face-to-face"],
        
        "Lack of personalization/research": ["personalization", "research", "generic", "specific", "tailored", "business", "knowledge"],
        "Insufficient value demonstration": ["value", "benefit", "solution", "roi", "relevance", "persuasive", "price"],
        "Poor objection handling": ["objection", "concern", "address", "overcome", "resistance", "doubt"],
        "Communication issues (clarity, filler words)": ["clarity", "filler", "jargon", "rambling", "concise", "word"],
        "Call structure and organization problems": ["structure", "organization", "prepared", "flow", "agenda", "abrupt", "ending"]
    }
    
    # Score each category based on keyword matches
    scores = {}
    for category in categories:
        score = 0
        if category in keywords:
            for keyword in keywords[category]:
                if keyword.lower() in point_lower:
                    score += 1
        scores[category] = score
    
    # Find category with highest score
    best_match = max(scores.items(), key=lambda x: x[1])
    
    # If no good match (score 0), try checking each category manually
    if best_match[1] == 0:
        for category in categories:
            # Very simple matching - check if any words from category appear in point
            category_words = set(category.lower().split())
            point_words = set(point_lower.split())
            if category_words.intersection(point_words):
                return category
        return categories[0]  # Default to first category if no match
    
    return best_match[0]

def categorize_points_by_call(calls_data):
    """
    Categorize points but track which calls they appear in to avoid duplicate counts
    Returns a dictionary of categories with sets of call IDs
    """
    strength_call_map = {category: set() for category in PREDEFINED_STRENGTHS}
    weakness_call_map = {category: set() for category in PREDEFINED_WEAKNESSES}
    
    for i, call in enumerate(calls_data):
        call_id = i + 1  # Simple call ID (position in list)
        
        # Process strengths
        if call['strengths']:
            try:
                strengths = json.loads(call['strengths'])
                for strength in strengths:
                    category = find_best_category_match(strength, PREDEFINED_STRENGTHS)
                    strength_call_map[category].add(call_id)
            except json.JSONDecodeError:
                pass
        
        # Process weaknesses
        if call['weaknesses']:
            try:
                weaknesses = json.loads(call['weaknesses'])
                for weakness in weaknesses:
                    category = find_best_category_match(weakness, PREDEFINED_WEAKNESSES)
                    weakness_call_map[category].add(call_id)
            except json.JSONDecodeError:
                pass
    
    # Convert to counts
    strength_counts = {category: len(call_ids) for category, call_ids in strength_call_map.items()}
    weakness_counts = {category: len(call_ids) for category, call_ids in weakness_call_map.items()}
    
    return strength_counts, weakness_counts

def extract_objections_from_transcript(transcript):
    """
    Extract potential objections from a transcript using GPT-4o
    Returns a list of objection phrases
    """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert at identifying customer objections in sales calls."},
                {"role": "user", "content": f"""Please analyze this sales call transcript and identify all customer objections. 
                List ONLY the objections as bullet points without any additional commentary.
                
                If there are no clear objections, respond with "No objections identified."
                
                Transcript:
                {transcript}
                """}
            ],
            temperature=0.5
        )
        
        content = response["choices"][0]["message"]["content"].strip()
        
        if "No objections identified" in content:
            return []
            
        # Extract bullet points
        objections = [line.strip().lstrip('•').lstrip('-').strip() for line in content.split('\n') 
                    if line.strip().startswith('•') or line.strip().startswith('-')]
        
        return objections
        
    except Exception as e:
        print(f"ERROR during objection extraction: {e}")
        return []

def categorize_objection(objection):
    """Find the best matching objection category"""
    objection_lower = objection.lower()
    
    # Keyword matching for objection categories
    keywords = {
        "Price/budget concerns": ["price", "cost", "expensive", "budget", "afford", "money", "investment", "cheaper", "discount", "roi"],
        "Need more time to decide": ["time", "think about", "consider", "not ready", "too soon", "later", "next quarter", "need time", "rushed"],
        "Need to consult others": ["boss", "manager", "team", "committee", "board", "discuss", "approval", "decision maker", "consult", "other people"],
        "Already using a competitor": ["already using", "competitor", "current provider", "current solution", "contract", "committed", "renewal", "switching costs"],
        "No perceived need/value": ["don't need", "no need", "why", "benefit", "value", "problem", "solution", "not interested", "relevance", "priority"],
        "Past negative experience": ["before", "previous", "experience", "didn't work", "issues", "problems", "tried", "failed", "disappointed"],
        "Implementation concerns": ["complex", "difficult", "implement", "setup", "integration", "technical", "support", "resources", "training"],
        "Contract/terms issues": ["contract", "terms", "agreement", "legal", "review", "commitment", "cancel", "policy", "guarantee", "warranty"]
    }
    
    # Score each category
    scores = {}
    for category in PREDEFINED_OBJECTIONS:
        score = 0
        if category in keywords:
            for keyword in keywords[category]:
                if keyword in objection_lower:
                    score += 1
        scores[category] = score
    
    # Find category with highest score
    best_match = max(scores.items(), key=lambda x: x[1])
    
    # If no good match (score 0), use a default
    if best_match[1] == 0:
        # Try checking for word overlap
        for category in PREDEFINED_OBJECTIONS:
            category_words = set(category.lower().split())
            objection_words = set(objection_lower.split())
            if category_words.intersection(objection_words):
                return category
        return "Other objections"  # Default if no match
    
    return best_match[0]

def analyze_objection_trends(calls_data):
    """
    Analyze objections across all calls to identify trends
    Returns a dictionary mapping objection categories to counts
    """
    objection_counts = {category: 0 for category in PREDEFINED_OBJECTIONS}
    objection_counts["Other objections"] = 0  # Add an "Other" category
    
    for call in calls_data:
        if call['objections']:
            try:
                objections = json.loads(call['objections'])
                for objection in objections:
                    category = categorize_objection(objection)
                    objection_counts[category] += 1
            except json.JSONDecodeError:
                pass
    
    # Sort by frequency
    sorted_objections = sorted(objection_counts.items(), key=lambda x: x[1], reverse=True)
    
    return sorted_objections

@app.route('/reports')
def reports():
    conn = get_db_connection()
    # Get aggregated strengths and weaknesses
    calls = conn.execute('SELECT strengths, weaknesses, objections, transcript FROM calls').fetchall()
    conn.close()
    
    # Categorize points by call to avoid duplicate counting
    strength_counts, weakness_counts = categorize_points_by_call(calls)
    
    # Convert to list of tuples and sort by frequency
    top_strengths = sorted([(cat, count) for cat, count in strength_counts.items()], key=lambda x: x[1], reverse=True)
    top_weaknesses = sorted([(cat, count) for cat, count in weakness_counts.items()], key=lambda x: x[1], reverse=True)
    
    # Get objection trends
    objection_trends = analyze_objection_trends(calls)
    
    # Extract the top 3 for improvement recommendations
    top_3_strengths = [s for s in top_strengths if s[1] > 0][:3] 
    top_3_weaknesses = [w for w in top_weaknesses if w[1] > 0][:3]
    
    # Generate improvement paragraph with specific suggestions
    improvement_paragraph = generate_improvement_paragraph(top_3_strengths, top_3_weaknesses)
    
    return render_template('reports.html', 
                          top_strengths=top_strengths, 
                          top_weaknesses=top_weaknesses,
                          top_3_strengths=top_3_strengths,
                          top_3_weaknesses=top_3_weaknesses,
                          objection_trends=objection_trends,
                          improvement_paragraph=improvement_paragraph,
                          total_calls=len(calls))

def generate_improvement_paragraph(strengths, weaknesses):
    """Generate a personalized improvement plan with specific tips"""
    if not weaknesses:
        return "Not enough data to generate improvement suggestions. Analyze more calls to get personalized recommendations."
    
    # Build a more beautifully formatted improvement plan with HTML
    paragraph = "<div class='improvement-section'>"
    
    # Add improvement suggestions for weaknesses
    paragraph += "<div class='improvement-area'>"
    paragraph += "<h3>Focus Areas</h3>"
    
    for weakness, count in weaknesses:
        if count > 0:
            if weakness == "Lack of personalization/research":
                suggestion = "Develop pre-call research templates and allocate specific time for prospect research. Before your next call, research the client's company and note 3 specific points to mention."
            elif weakness == "Insufficient value demonstration":
                suggestion = "Create case studies showing ROI for different client types. In your next call, prepare specific examples using the Problem-Solution-Result framework."
            elif weakness == "Poor objection handling":
                suggestion = "Build a personal objection handbook with proven responses. Practice the listen-acknowledge-clarify-respond-confirm process for addressing concerns."
            elif weakness == "Communication issues (clarity, filler words)":
                suggestion = "Record practice sessions to identify filler words. Use a reminder note during calls and practice pausing instead of using fillers."
            elif weakness == "Call structure and organization problems":
                suggestion = "Create call templates with clear sections for different scenarios. Plan your call flow in advance with specific transition phrases."
            else:
                suggestion = "Focus on improving this area."
                
            paragraph += f"<div class='improvement-item'>"
            paragraph += f"<h4>{weakness}</h4>"
            paragraph += f"<p>{suggestion}</p>"
            paragraph += "</div>"
    
    paragraph += "</div>"  # Close improvement-area
    
    # Add recommendations for strengths
    if strengths:
        paragraph += "<div class='strength-area'>"
        paragraph += "<h3>Leverage Your Strengths</h3>"
        
        for strength, count in strengths:
            if count > 0:
                if strength == "Rapport building and relationship skills":
                    advice = "Use your relationship skills to uncover deeper client needs. Connect rapport-building to business value discussions."
                elif strength == "Active listening and empathy":
                    advice = "Take detailed notes during calls to capture insights. Ask reflective questions showing you understand their situation."
                elif strength == "Effective questioning techniques":
                    advice = "Develop a systematic questioning framework. Move conversations from problem exploration to solution validation."
                elif strength == "Clear communication and presentation":
                    advice = "Create custom presentation templates. Focus more on quantifiable outcomes in your clear explanations."
                elif strength == "Closing and follow-up skills":
                    advice = "Develop a follow-up system with prepared materials for each scenario. Use your closing skills to secure clearer commitments."
                else:
                    advice = "Continue leveraging this strength."
                    
                paragraph += f"<div class='strength-item'>"
                paragraph += f"<h4>{strength}</h4>"
                paragraph += f"<p>{advice}</p>"
                paragraph += "</div>"
        
        paragraph += "</div>"  # Close strength-area
    
    # Add action plan
    paragraph += "<div class='action-plan'>"
    paragraph += "<h3>Action Plan</h3>"
    paragraph += "<ol>"
    paragraph += f"<li>Focus first on addressing <strong>{weaknesses[0][0]}</strong></li>"
    paragraph += "<li>Schedule 30 minutes weekly to practice these specific skills</li>"
    paragraph += "<li>Review your calls regularly to track improvement</li>"
    paragraph += "<li>Measure success by increased engagement and follow-up requests</li>"
    paragraph += "</ol>"
    paragraph += "</div>"  # Close action-plan
    
    paragraph += "</div>"  # Close improvement-section
    
    return paragraph

@app.route('/transcribe_analyze', methods=['POST'])
def transcribe_analyze():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    # Create temporary file
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, file.filename)
    file.save(temp_path)
    
    try:
        # Transcribe the audio
        transcript = transcribe_audio_whisper(temp_path)
        
        # Analyze the transcript
        feedback, strengths, weaknesses, rating = analyze_sales_call_gpt4(transcript)
        
        # Extract objections
        objections = extract_objections_from_transcript(transcript)
        
        # Save to database
        conn = get_db_connection()
        conn.execute(
            'INSERT INTO calls (filename, transcript, feedback, strengths, weaknesses, objections, overall_rating) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (file.filename, transcript, feedback, json.dumps(strengths), json.dumps(weaknesses), json.dumps(objections), rating)
        )
        conn.commit()
        conn.close()
        
        return jsonify({
            'transcript': transcript,
            'feedback': feedback,
            'strengths': strengths,
            'weaknesses': weaknesses,
            'objections': objections,
            'rating': rating
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_path):
            os.remove(temp_path)

def transcribe_audio_whisper(file_path):
    """
    Transcribes an audio file using OpenAI's Whisper API
    """
    try:
        with open(file_path, "rb") as audio_file:
            # Using OpenAI API version 0.28.1
            response = openai.Audio.transcribe(
                "whisper-1",
                audio_file
            )
            
        return response["text"]
        
    except Exception as e:
        print(f"ERROR during transcription: {e}")
        raise Exception(f"Transcription error: {e}")

def analyze_sales_call_gpt4(transcript):
    """
    Sends the transcript to GPT-4o for a "Sales Coach" style analysis
    Returns feedback, list of strengths, list of weaknesses, and overall rating (1-10)
    """
    try:
        # Enhanced prompt to extract specific data points
        response = openai.ChatCompletion.create(
            model="gpt-4o",  # Using GPT-4o
            messages=[
                {"role": "system", "content": "You are a sales call evaluation expert. Analyze the sales call transcript and provide detailed feedback. Extract key strengths and weaknesses as bullet points, and provide an overall rating from 1-10."},
                {"role": "user", "content": f"""Please evaluate the following sales call transcript. In your analysis:
                
1. Provide detailed feedback on sales effectiveness
2. List 3-5 specific strengths as concise bullet points
3. List 3-5 specific areas for improvement as concise bullet points
4. Rate the overall sales performance on a scale of 1-10 (with 10 being excellent)

Format your response with clear sections:

DETAILED FEEDBACK:
[Your comprehensive feedback here]

STRENGTHS:
- [Strength 1]
- [Strength 2]
- [Etc.]

WEAKNESSES:
- [Weakness 1]
- [Weakness 2]
- [Etc.]

OVERALL RATING:
[1-10]

Transcript:
{transcript}
                """}
            ],
            temperature=0.7
        )
        
        # Extract the content from the response
        content = response["choices"][0]["message"]["content"]
        
        # Parse the response to extract strengths, weaknesses, and rating
        detailed_feedback = ""
        strengths = []
        weaknesses = []
        rating = 5  # Default rating
        
        # Simple parsing of the sections using split by double newline
        sections = content.split("\n\n")
        for section in sections:
            if section.startswith("DETAILED FEEDBACK:"):
                detailed_feedback = section.replace("DETAILED FEEDBACK:", "").strip()
            elif section.startswith("STRENGTHS:"):
                strength_text = section.replace("STRENGTHS:", "").strip()
                strengths = [s.strip().lstrip("- ") for s in strength_text.split("\n") if s.strip()]
            elif section.startswith("WEAKNESSES:"):
                weakness_text = section.replace("WEAKNESSES:", "").strip()
                weaknesses = [w.strip().lstrip("- ") for w in weakness_text.split("\n") if w.strip()]
            elif section.startswith("OVERALL RATING:"):
                rating_text = section.replace("OVERALL RATING:", "").strip()
                # Improved rating extraction - using regex to find numbers
                rating_match = re.search(r'(\d+)', rating_text)
                if rating_match:
                    try:
                        rating = int(rating_match.group(1))
                        # Ensure rating is within 1-10 range
                        rating = max(1, min(10, rating))
                    except ValueError:
                        rating = 5  # Default if parsing fails
        
        # If no sections were found with standard parsing, try a more flexible approach
        if not detailed_feedback and not strengths and not weaknesses:
            # Look for the rating first with a more flexible regex
            rating_match = re.search(r'OVERALL RATING:?\s*(\d+)', content)
            if rating_match:
                try:
                    rating = int(rating_match.group(1))
                    rating = max(1, min(10, rating))
                except ValueError:
                    pass
                
            # Try to extract strengths and weaknesses using a more flexible approach
            strength_section = re.search(r'STRENGTHS:(.+?)(?=WEAKNESSES:|OVERALL RATING:|$)', content, re.DOTALL)
            if strength_section:
                strength_text = strength_section.group(1).strip()
                strengths = [s.strip().lstrip("- ") for s in strength_text.split("\n") if s.strip() and not s.startswith("STRENGTHS:")]
            
            weakness_section = re.search(r'WEAKNESSES:(.+?)(?=OVERALL RATING:|$)', content, re.DOTALL)
            if weakness_section:
                weakness_text = weakness_section.group(1).strip()
                weaknesses = [w.strip().lstrip("- ") for w in weakness_text.split("\n") if w.strip() and not w.startswith("WEAKNESSES:")]
            
            # Use the whole content as feedback if we couldn't parse specific sections
            detailed_feedback = content
        
        # Final check to make sure we have reasonable results
        if not strengths:
            strengths = ["Effective communication"]
        
        if not weaknesses:
            weaknesses = ["Could improve call structure"]
        
        return detailed_feedback, strengths, weaknesses, rating
        
    except Exception as e:
        print(f"ERROR during GPT-4o analysis: {e}")
        raise Exception(f"GPT-4o Analysis error: {e}")

if __name__ == '__main__':
    app.run(debug=True)
