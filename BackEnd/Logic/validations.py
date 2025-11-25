# backend/logic/validators.py

def validate_group_members(members):
    if len(members) < 2:
        return False, "At least 2 members required"
    return True, ""
