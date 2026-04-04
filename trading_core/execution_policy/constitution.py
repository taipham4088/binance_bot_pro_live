from .net_position import NetPosition


class ExecutionConstitution:

    @staticmethod
    def validate_authority(intent):
        # future: role based
        if intent.type == "EMERGENCY" and intent.source != "system":
            raise PermissionError("Emergency intent only allowed from system")

    @staticmethod
    def validate_position(position: NetPosition):
        position.validate()
