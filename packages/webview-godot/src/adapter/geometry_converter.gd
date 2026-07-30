extends RefCounted


static func full_screen() -> Dictionary:
	return {
		"x": 0.0,
		"y": 0.0,
		"width": 1.0,
		"height": 1.0,
	}


static func from_godot_rect(rectangle: Rect2, viewport_size: Vector2) -> Dictionary:
	if viewport_size.x <= 0.0 or viewport_size.y <= 0.0:
		return {
			"x": NAN,
			"y": NAN,
			"width": NAN,
			"height": NAN,
		}
	return {
		"x": rectangle.position.x / viewport_size.x,
		"y": rectangle.position.y / viewport_size.y,
		"width": rectangle.size.x / viewport_size.x,
		"height": rectangle.size.y / viewport_size.y,
	}
