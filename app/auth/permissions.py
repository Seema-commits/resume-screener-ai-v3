"""
The one place that decides who may do what. Every page and action
calls these functions; nothing else checks roles directly, and the
LLM never takes part in permission decisions.
"""

SUPERADMIN = "superadmin"
HR_MANAGER = "hr_manager"
HR_EXECUTIVE = "hr_executive"

ROLE_LABELS = {
    SUPERADMIN: "Superadmin",
    HR_MANAGER: "HR Manager",
    HR_EXECUTIVE: "HR Executive",
}

ACTIONS = {
    "run_scan",         # screen resumes
    "view_own_scans",   # own scan history
    "view_team_scans",  # every scan in the user's own org
    "view_all_scans",   # every scan in every org
    "manage_users",     # open the Users page (what exactly: can_manage)
    "manage_orgs",      # create organizations
    "view_settings",
    "view_logs",
}

ROLE_PERMISSIONS = {
    SUPERADMIN: ACTIONS,
    HR_MANAGER: {"run_scan", "view_own_scans", "view_team_scans", "manage_users"},
    HR_EXECUTIVE: {"run_scan", "view_own_scans"},
}

# Which roles each role may create and manage. Superadmins are only
# created with the bootstrap secret or the create_superadmin script.
MANAGEABLE_ROLES = {
    SUPERADMIN: {HR_MANAGER, HR_EXECUTIVE},
    HR_MANAGER: {HR_EXECUTIVE},
    HR_EXECUTIVE: set(),
}


def has_permission(user, action):
    """True if the (active, logged-in) user's role allows the action."""

    if user is None or action not in ACTIONS:
        return False

    return action in ROLE_PERMISSIONS.get(user.role, set())


def can_manage(actor, target_role, target_org_id, target_user_id=None):
    """
    True if `actor` may create - or deactivate, reactivate, unlock
    or reset the password of - a user with this role in this org.
    An HR Manager is limited to HR Executives in her own org; nobody
    manages their own account here.
    """

    if not has_permission(actor, "manage_users"):
        return False

    if target_user_id is not None and target_user_id == actor.id:
        return False

    if target_role not in MANAGEABLE_ROLES.get(actor.role, set()):
        return False

    if actor.role == SUPERADMIN:
        return True

    return target_org_id == actor.org_id
