"""HTTP controllers (Flask blueprints).

Routes only parse the request, call a service, and render/redirect. All rules
live in the service/domain layers so controllers stay thin.
"""
