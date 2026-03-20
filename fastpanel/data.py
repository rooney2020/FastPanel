import uuid
from fastpanel.constants import TYPE_CMD, SUB_APP

class ComponentData:
    def __init__(self, name="", comp_type=TYPE_CMD, sub_type=SUB_APP, cmd="", show_output=False,
                 icon="", path="", x=0, y=0, w=300, h=200, uid=None,
                 param_hints=None, param_defaults=None, group_id=None, pre_cmd="",
                 refresh_interval=300):
        self.id = uid or str(uuid.uuid4())
        self.comp_type = comp_type
        self.sub_type = sub_type
        self.name = name
        self.cmd = cmd
        self.show_output = show_output
        self.icon = icon
        self.path = path
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.param_hints = param_hints or []
        self.param_defaults = param_defaults or []
        self._group_id = group_id
        self.pre_cmd = pre_cmd
        self.refresh_interval = refresh_interval

    def to_dict(self):
        d = {
            "id": self.id, "type": self.comp_type, "sub_type": self.sub_type,
            "name": self.name, "cmd": self.cmd, "show_output": self.show_output,
            "icon": self.icon, "path": self.path,
            "x": self.x, "y": self.y, "w": self.w, "h": self.h,
        }
        if self.param_hints:
            d["param_hints"] = self.param_hints
        if self.param_defaults:
            d["param_defaults"] = self.param_defaults
        if self._group_id:
            d["group_id"] = self._group_id
        if self.pre_cmd:
            d["pre_cmd"] = self.pre_cmd
        if self.refresh_interval != 300:
            d["refresh_interval"] = self.refresh_interval
        return d

    @staticmethod
    def from_dict(d):
        return ComponentData(
            name=d.get("name", ""), comp_type=d.get("type", TYPE_CMD),
            sub_type=d.get("sub_type", SUB_APP),
            cmd=d.get("cmd", ""), show_output=d.get("show_output", False),
            icon=d.get("icon", ""), path=d.get("path", ""),
            x=d.get("x", 0), y=d.get("y", 0),
            w=d.get("w", 300), h=d.get("h", 200), uid=d.get("id"),
            param_hints=d.get("param_hints", []),
            param_defaults=d.get("param_defaults", []),
            group_id=d.get("group_id"),
            pre_cmd=d.get("pre_cmd", ""),
            refresh_interval=d.get("refresh_interval", 300),
        )


class PanelData:
    def __init__(self, name="默认", uid=None, components=None):
        self.id = uid or str(uuid.uuid4())
        self.name = name
        self.components: list[ComponentData] = components or []

    def to_dict(self):
        return {"id": self.id, "name": self.name,
                "components": [c.to_dict() for c in self.components]}

    @staticmethod
    def from_dict(d):
        comps = [ComponentData.from_dict(c) for c in d.get("components", [])]
        return PanelData(name=d["name"], uid=d.get("id"), components=comps)


# ---------------------------------------------------------------------------
# Drag/Resize mixin
# ---------------------------------------------------------------------------

