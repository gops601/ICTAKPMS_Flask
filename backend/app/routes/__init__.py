def register_blueprints(app):
    from app.extensions import api
    from . import admin, auth, batches, dashboard, domains, feedback, health, imports, notifications, ous, portals, problem_statements, projects, proposals, review_dates, reviews, scrum, srs, students

    app.register_blueprint(health.bp)
    for module in (auth, admin, ous, domains, batches, students, feedback, imports, problem_statements, projects, proposals, notifications, srs, scrum, reviews, dashboard, review_dates, portals):
        api.register_blueprint(module.bp)
