def test_import():
    from app.main import app
    assert app.title.startswith("大学生运动计划")
