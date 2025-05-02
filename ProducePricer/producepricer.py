from flask import Flask, redirect, render_template, url_for
from forms import SignUp, Login
app = Flask(__name__)

# secret key
app.config['SECRET_KEY'] = '33d151aee312625a351143d17aeb358f'

# route for the root URL
@app.route('/')
@app.route('/home')
def home():
    return render_template('home.html')

# about page
@app.route('/about')
def about():
    return render_template('about.html')

# signup page
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    form = SignUp()
    if form.validate_on_submit():
        # process the form data
        return redirect(url_for('home'))
    return render_template('signup.html', title='Sign Up', form=form)

# login page
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = Login()
    if form.validate_on_submit():
        # process the form data
        return redirect(url_for('home'))
    return render_template('login.html', title='Login', form=form)

# only true if this file is run directly
if __name__ == '__main__':
    app.run(debug=True)