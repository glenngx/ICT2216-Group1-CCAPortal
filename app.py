from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def home():
    ccas = [
        {"id": 1, "name": "Basketball Club", "description": "Improve your basketball skills and participate in inter-school competitions."},
        {"id": 2, "name": "Debate Society", "description": "Develop critical thinking and public speaking through competitive debate."},
    ]
    
    available_polls = [
        {"id": 1, "title": "Training Schedule", "end_date": "2025-05-25", "cca": "Basketball Club"},
        {"id": 2, "title": "Competition Team Selection", "end_date": "2025-05-30", "cca": "Debate Society"}
    ]
    
    return render_template('dashboard.html', ccas=ccas, available_polls=available_polls)

if __name__ == '__main__':
    app.run(debug=True)