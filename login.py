from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    flash,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import pyodbc
from datetime import datetime
from collections import defaultdict
import os


app = Flask(__name__)

# Database configuration from environment variables
DB_DRIVER = os.environ.get("DB_DRIVER", "{ODBC Driver 17 for SQL Server}")
DB_SERVER = os.environ.get("DB_SERVER", "localhost\\SQLEXPRESS")
DB_NAME = os.environ.get("DB_NAME", "evsuDB")
DB_USER = os.environ.get("DB_USER", "")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_CONN_STRING = os.environ.get("DB_CONN_STRING", "")

# Configure SQLAlchemy with connection string from environment variables
if DB_CONN_STRING:
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"mssql+pyodbc:///?odbc_connect={DB_CONN_STRING}"
    )
else:
    if DB_USER and DB_PASSWORD:
        conn_str = f"DRIVER={DB_DRIVER};SERVER={DB_SERVER};DATABASE={DB_NAME};UID={DB_USER};PWD={DB_PASSWORD}"
    else:
        conn_str = f"DRIVER={DB_DRIVER};SERVER={DB_SERVER};DATABASE={DB_NAME};Trusted_Connection=yes"

    app.config["SQLALCHEMY_DATABASE_URI"] = f"mssql+pyodbc:///?odbc_connect={conn_str}"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "your_secret_key")

db = SQLAlchemy(app)


def get_db_connection():
    if DB_CONN_STRING:
        return pyodbc.connect(DB_CONN_STRING)
    elif DB_USER and DB_PASSWORD:
        conn_str = f"DRIVER={DB_DRIVER};SERVER={DB_SERVER};DATABASE={DB_NAME};UID={DB_USER};PWD={DB_PASSWORD}"
    else:
        conn_str = f"DRIVER={DB_DRIVER};SERVER={DB_SERVER};DATABASE={DB_NAME};Trusted_Connection=yes"

    return pyodbc.connect(conn_str)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)


# Updated DB_CONFIG dictionary
DB_CONFIG = {"driver": DB_DRIVER, "server": DB_SERVER, "database": DB_NAME}

# Add username/password if not using trusted connection
if DB_USER and DB_PASSWORD:
    DB_CONFIG["uid"] = DB_USER
    DB_CONFIG["pwd"] = DB_PASSWORD
else:
    DB_CONFIG["trusted_connection"] = "yes"

# Create database tables if they don't exist
with app.app_context():
    db.create_all()


@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            print(user)
            return redirect(url_for("dashboard"))
        else:
            return render_template("index.html", error="Invalid username or password")

    return render_template("index.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if password != confirm_password:
            return render_template("index.html", error="Passwords do not match")

        if User.query.filter_by(username=username).first():
            return render_template("index.html", error="Username already exists")

        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for("login"))

    return render_template("index.html")


@app.route("/dashboard")
def dashboard():
    if "user_id" in session:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Query to fetch all relevant SDG, project status, and college campus data
            cursor.execute("""
                SELECT sdg, projectstatus, collegecampus, projectdate
                FROM dbo.Projects
                WHERE sdg IS NOT NULL AND projectstatus IN ('Completed', 'In Progress')
            """)

            results = cursor.fetchall()

            sdg_stats = {i: {"completed": 0, "in_progress": 0} for i in range(1, 18)}
            total_projects = 0
            completed_count = 0
            in_progress_count = 0
            collegecampus_counts = defaultdict(int)
            yearly_programs = defaultdict(int)

            print("Total rows in results:", len(results))

            for row in results:
                sdgs = row[0].split(",") if row[0] else []
                projectstatus = row[1]
                collegecampus = row[2]
                projectdate = row[3]

                print("Project Details:")
                print(f"  SDGs: {sdgs}")
                print(f"  Status: {projectstatus}")
                print(f"  Campus: {collegecampus}")

                total_projects += 1

                # Process project status
                if projectstatus == "Completed":
                    completed_count += 1
                elif projectstatus == "In Progress":
                    in_progress_count += 1

                # Process SDGs
                for sdg in sdgs:
                    if not sdg.strip():  # Skip empty SDG values
                        continue
                    try:
                        sdg_number = int(sdg)  # Convert SDG to integer
                    except ValueError:
                        print(f"  Warning: Invalid SDG value: {sdg}")
                        continue

                    if projectstatus == "Completed":
                        sdg_stats[sdg_number]["completed"] += 1
                    elif projectstatus == "In Progress":
                        sdg_stats[sdg_number]["in_progress"] += 1

                # Count campus occurrences
                collegecampus_counts[collegecampus] += 1

                print("\nFinal Counts:")
                print(f"Total Projects: {total_projects}")
                print(f"Completed Projects: {completed_count}")
                print(f"In Progress Projects: {in_progress_count}")

                # Process project date and increment yearly counts
                if projectdate:
                    try:
                        year = datetime.strptime(projectdate, "%B %Y").year
                    except ValueError:
                        try:
                            year = datetime.strptime(projectdate, "%B %d, %Y").year
                        except ValueError:
                            continue
                    yearly_programs[year] += 1

            # Prepare data for charts
            collegecampus_labels = list(collegecampus_counts.keys())
            collegecampus_data = list(collegecampus_counts.values())
            start_year = 2020
            end_year = max(yearly_programs.keys(), default=start_year)
            all_years = list(range(start_year, end_year + 1))

            program_counts = [yearly_programs.get(year, 0) for year in all_years]

            cursor.close()
            conn.close()

            return render_template(
                "dashboard.html",
                sdg_stats=sdg_stats,
                total_projects=total_projects,
                completed_count=completed_count,
                in_progress_count=in_progress_count,
                collegecampus_labels=collegecampus_labels,
                collegecampus_data=collegecampus_data,
                years=all_years,
                program_counts=program_counts,
            )

        except Exception as e:
            print(f"Error fetching stats: {str(e)}")
            return jsonify({"status": "error", "message": str(e)}), 500

    else:
        flash("You must be logged in to access the dashboard.")
        return redirect(url_for("login"))


# Helper function to check login status
def is_logged_in():
    """
    Helper function to check if a user is logged in.
    """
    return "user_id" in session


# 1
@app.route("/dashboard2")
def dashboard2():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Query to fetch all relevant SDG, project status, and college campus data
        cursor.execute(""" 
            SELECT sdg, projectstatus, collegecampus, projectdate
            FROM dbo.Projects
            WHERE sdg IS NOT NULL AND projectstatus IN ('Completed', 'In Progress')
        """)

        # Fetch the results
        results = cursor.fetchall()

        # Initialize a dictionary to store the SDG counts
        sdg_stats = {i: {"completed": 0, "in_progress": 0} for i in range(1, 18)}

        # Initialize counters for overall counts
        total_projects = 0
        completed_count = 0
        in_progress_count = 0

        # Initialize a dictionary to store college campus counts for the doughnut chart
        collegecampus_counts = defaultdict(int)

        # Initialize a dictionary to store the number of projects per year for the line chart
        yearly_programs = defaultdict(int)

        # Process the results and count the occurrences of each SDG, project status, college campus, and project year
        for row in results:
            sdgs = row[0].split(",")  # Split the SDG field into individual SDGs
            projectstatus = row[1]
            collegecampus = row[2]
            projectdate = row[3]

            total_projects += 1  # Increment the total projects counter

            # Count SDG status (Completed vs In Progress)
            for sdg in sdgs:
                if sdg.strip():  # Check if SDG is not empty
                    try:
                        sdg_number = int(sdg)  # Convert SDG to integer
                    except ValueError:
                        continue  # Skip if conversion fails (i.e., not a valid number)
                    if projectstatus == "Completed":
                        sdg_stats[sdg_number]["completed"] += 1
                        completed_count += 1  # Increment completed counter
                    elif projectstatus == "In Progress":
                        sdg_stats[sdg_number]["in_progress"] += 1
                        in_progress_count += 1  # Increment in-progress counter

            # Count the college campus occurrences
            if collegecampus.strip():  # Ensure college campus is not empty
                collegecampus_counts[collegecampus] += 1

            # Count the number of projects per year
            if projectdate:  # Only process if the projectdate is not None or empty
                try:
                    # Try to extract the year from the project date (in format "March 2024")
                    year = datetime.strptime(projectdate, "%B %Y").year
                except ValueError:
                    try:
                        # Try another format for specific dates like 'March 14, 2022'
                        year = datetime.strptime(projectdate, "%B %d, %Y").year
                    except ValueError:
                        continue  # Skip invalid date formats
                yearly_programs[year] += 1  # Increment the count for that year

        # Prepare data for the doughnut chart (College Campus)
        collegecampus_labels = list(collegecampus_counts.keys())
        collegecampus_data = list(collegecampus_counts.values())

        # Prepare data for the line chart (Projects per year)
        start_year = 2020
        end_year = max(yearly_programs.keys(), default=start_year)
        all_years = list(
            range(start_year, end_year + 1)
        )  # Ensure the range starts from 2020

        program_counts = []
        for year in all_years:
            program_counts.append(
                yearly_programs.get(year, 0)
            )  # If the year has no data, default to 0

        # Close the database connection
        cursor.close()
        conn.close()

        # Pass the SDG stats, total counts, college campus data, and line chart data to the template
        return render_template(
            "dashboard2.html",
            sdg_stats=sdg_stats,
            total_projects=total_projects,
            completed_count=completed_count,
            in_progress_count=in_progress_count,
            collegecampus_labels=collegecampus_labels,
            collegecampus_data=collegecampus_data,
            years=all_years,
            program_counts=program_counts,
        )

    except Exception as e:
        print(f"Error occurred in dashboard2 route: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/main-campus")
def main_campus():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT projectid, title, leader FROM dbo.Projects")
        programs = [
            {"projectid": row[0], "title": row[1], "leader": row[2]}
            for row in cursor.fetchall()
        ]

        print("Programs fetched:")
        for program in programs:
            print(f"Project ID: {program['projectid']}, Title: {program['title']}")

        cursor.close()
        conn.close()

        return render_template("main-campus.html", programs=programs)
    except Exception as e:
        print(f"Error in main_campus route: {str(e)}")
        return f"An error occurred: {str(e)}", 500


@app.route("/main-campus2")
def main_campus2():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT projectid, title, leader FROM dbo.Projects")
        programs = [
            {"projectid": row[0], "title": row[1], "leader": row[2]}
            for row in cursor.fetchall()
        ]

        print("Programs fetched:")
        for program in programs:
            print(f"Project ID: {program['projectid']}, Title: {program['title']}")

        cursor.close()
        conn.close()

        return render_template("main-campus2.html", programs=programs)
    except Exception as e:
        print(f"Error in main_campus route: {str(e)}")
        return f"An error occurred: {str(e)}", 500


@app.route("/api/projects")
def get_projects():
    projects = get_project_locations()
    return jsonify(projects)


@app.route("/logout")
def logout():
    # Clear the session to log out the user
    session.clear()

    # Redirect to the login page (or index page)
    return redirect(url_for("login"))  # Assuming the login route is 'login'


@app.route("/map")
def map():
    return render_template("map.html")


@app.route("/map2")
def map2():
    return render_template("map2.html")


@app.route("/extension-program-management")
def extension_program_management():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM dbo.Projects")
        columns = [column[0] for column in cursor.description]
        programs = [dict(zip(columns, row)) for row in cursor.fetchall()]

        cursor.close()
        conn.close()

        return render_template("crud.html", programs=programs)

    except Exception as e:
        return f"An error occurred: {str(e)}", 500


def get_project_locations():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
        SELECT *
        FROM dbo.Projects
        WHERE x IS NOT NULL AND y IS NOT NULL
        """

        cursor.execute(query)
        columns = [column[0] for column in cursor.description]
        projects = []

        for row in cursor:
            project = dict(zip(columns, row))

            for key, value in project.items():
                if isinstance(value, datetime):
                    project[key] = value.strftime("%Y-%m-%d")
                elif isinstance(value, (float, int)):
                    project[key] = str(value)
                elif value is None:
                    project[key] = ""

            project["lng"] = project.pop("x")
            project["lat"] = project.pop("y")

            if project.get("link"):
                project["link"] = f"/static/pdfs/{project['link']}"

            projects.append(project)

        cursor.close()
        conn.close()
        return projects
    except Exception as e:
        print(f"Error in get_project_locations: {str(e)}")
        return []


# 2
@app.route("/add-program", methods=["POST"])
def add_program():
    try:
        # Collect multiple SDG values as a list
        sdg_goals = request.form.getlist(
            "sdg[]"
        )  # Adjusting to handle multiple SDG values
        if not sdg_goals:
            print("SDG values are missing or empty.")
            return jsonify(
                {"status": "error", "message": "No SDG values provided."}
            ), 400
        else:
            sdg_string = ",".join(sdg_goals)  # Convert list to a comma-separated string
            print(f"Received SDG values (backend): {sdg_string}")

        # Database connection and insertion
        conn = get_db_connection()
        cursor = conn.cursor()

        # Generating a new project ID (adjusted for MSSQL)
        new_project_id = cursor.execute(
            "SELECT ISNULL(MAX(projectid), 0) + 1 FROM dbo.Projects"
        ).fetchval()

        data = {
            "projectid": new_project_id,
            "title": request.form.get("title"),
            "projectlocation": request.form.get("projectlocation"),
            "leader": request.form.get("leader"),
            "assistant": request.form.get("assistant"),
            "members": request.form.get("members"),
            "projectdate": request.form.get("projectdate"),
            "duration": request.form.get("duration"),
            "projectstatus": request.form.get("projectstatus"),
            "link": request.form.get("link"),
            "x": request.form.get("x"),
            "y": request.form.get("y"),
            "sdg": sdg_string,  # Save the SDG values as a comma-separated string
            "collegecampus": request.form.get("collegecampus"),
        }

        print(f"Final Data sent to DB: {data}")  # Debugging Output

        # Insert into the database
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?" for _ in data])
        cursor.execute(
            f"INSERT INTO dbo.Projects ({columns}) VALUES ({placeholders})",
            list(data.values()),
        )
        conn.commit()

        cursor.close()
        conn.close()
        return jsonify({"status": "success", "message": "Program added successfully"})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# 3
@app.route("/get-program/<int:projectid>", methods=["GET"])
def get_program(projectid):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Fetch the project by its ID
        cursor.execute("SELECT * FROM dbo.Projects WHERE projectid=?", projectid)
        columns = [column[0] for column in cursor.description]
        project = cursor.fetchone()

        cursor.close()
        conn.close()

        if project:
            project_dict = dict(zip(columns, project))

            # Process fields for proper formatting
            for key, value in project_dict.items():
                if isinstance(value, datetime):
                    project_dict[key] = value.strftime(
                        "%Y-%m-%d"
                    )  # Format datetime to 'YYYY-MM-DD'
                elif value is None:
                    project_dict[key] = ""
                elif key == "sdg" and value:
                    # Ensure SDG is returned as a clean comma-separated string
                    project_dict[key] = ",".join(
                        [sdg.strip() for sdg in value.split(",") if sdg.strip()]
                    )

            # Debugging: Log the processed project details
            print("Processed program details:", project_dict)

            return jsonify(project_dict)
        else:
            return jsonify({"status": "error", "message": "Project not found"}), 404

    except Exception as e:
        print(f"Error in get_program: {e}")  # Debugging output
        return jsonify({"status": "error", "message": str(e)}), 500


# 4
@app.route("/project-details/<int:projectid>", methods=["GET"])
def project_details(projectid):
    print(f"Received project ID: {projectid}")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM dbo.Projects WHERE projectid=?"
        print(f"Executing query: {query} with projectid: {projectid}")

        cursor.execute(query, (projectid,))
        columns = [column[0] for column in cursor.description]

        project = cursor.fetchone()

        cursor.close()
        conn.close()

        if project:
            project_dict = dict(zip(columns, project))

            for key, value in project_dict.items():
                if isinstance(value, datetime):
                    project_dict[key] = value.strftime("%Y-%m-%d")
                elif value is None:
                    project_dict[key] = ""

            print(f"Returning project: {project_dict}")
            return jsonify(project_dict)
        else:
            print(f"No project found for ID: {projectid}")
            return jsonify({"status": "error", "message": "Project not found"}), 404

    except Exception as e:
        print(f"Error fetching project details: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


# 5
@app.route("/edit-program/<int:projectid>", methods=["PUT"])
def edit_program(projectid):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get SDG values from the form
        sdg_goals = request.form.getlist("sdg[]")
        sdg_string = ",".join(sdg_goals) if sdg_goals else None

        # Prepare the update data
        data = {
            "title": request.form.get("title"),
            "projectlocation": request.form.get("projectlocation"),
            "leader": request.form.get("leader"),
            "assistant": request.form.get("assistant"),
            "members": request.form.get("members"),
            "projectdate": request.form.get("projectdate"),
            "duration": request.form.get("duration"),
            "projectstatus": request.form.get("projectstatus"),
            "link": request.form.get("link"),
            "x": request.form.get("x"),
            "y": request.form.get("y"),
            "sdg": sdg_string,
            "collegecampus": request.form.get("collegecampus"),
        }

        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}

        # Build the UPDATE query
        set_clause = ", ".join([f"{key} = ?" for key in data.keys()])
        query = f"UPDATE dbo.Projects SET {set_clause} WHERE projectid = ?"

        # Add the projectid to the values
        values = list(data.values()) + [projectid]

        # Execute the update
        cursor.execute(query, values)

        if cursor.rowcount == 0:
            return jsonify(
                {"status": "error", "message": "No program found with the given ID"}
            ), 404

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"status": "success", "message": "Program updated successfully"})

    except Exception as e:
        print(f"Error in edit_program: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


# 6
@app.route("/delete-program/<int:projectid>", methods=["DELETE"])
def delete_program(projectid):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM dbo.Projects WHERE projectid=?", projectid)
        project_exists = cursor.fetchone()[0] > 0

        if not project_exists:
            return jsonify({"status": "error", "message": "Project not found"}), 404
        cursor.execute("DELETE FROM dbo.Projects WHERE projectid=?", projectid)

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"status": "success", "message": "Program deleted successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# Add a health check endpoint for Render
@app.route("/health")
def health_check():
    return jsonify({"status": "healthy"}), 200


if __name__ == "__main__":
    # Use the PORT environment variable provided by Render
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
