import pytest
import os
import json

from django.contrib import auth
from django_scopes import scope

from cookbook.helper.ingredient_parser import IngredientParser
from cookbook.forms import ImportExportBase
from cookbook.tests.conftest import validate_recipe

from ._recipes import CUISINE_SIMPLE

from cookbook.integration.cuisine import *
from cookbook.helper.ingredient_parser import IngredientParser


@pytest.fixture
def user1(u1_s1, u2_s1, space_1):
    return auth.get_user(u1_s1)


def file_path(filename):
    ext = os.path.join("other", "test_data", filename)
    if "cookbook" in os.getcwd():
        return os.path.join(os.getcwd(), ext)
    else:
        return os.path.join(os.getcwd(), "cookbook", "tests", ext)


@pytest.mark.parametrize("arg", [
    "cuisine_simple.tex",
    "cuisine_complex.tex"
])
def test_get_recipe_from_file(arg, user1, space_1):
    request = type("", (object,), {"space": space_1, "user": user1})()
    with scope(space=space_1):
        cuisine = Cuisine(request, ImportExportBase.CUISINE)

        test_file = file_path(arg)
        with open(test_file, "r", encoding="UTF-8") as f:
            recipe = cuisine.get_recipe_from_file(f.read())

        # TODO: Validate recipe contents


def test_split_recipe_file(user1, space_1):
    request = type("", (object,), {"space": space_1, "user": user1})()
    with scope(space=space_1):
        cuisine = Cuisine(request, ImportExportBase.CUISINE)

        test_file = file_path("cuisine_collection.tex")
        with open(test_file, "r", encoding="UTF-8") as f:
            data_list = cuisine.split_recipe_file(f.read())

        assert len(data_list) == 2


def test_ingredient_parser():
    expectations = {
        "\\ingredient{1/2 pt}{milk}": (0.5, "pt", "milk", ""),
        "\\ingredient{2 oz}{butter}": (2, "oz", "butter", ""),
        "\\ingredient{5 oz}{self-raising flour}": (5, "oz", "self-raising flour", ""),
        "\\ing{3 tbsp}{sugar, granulated}": (3, "tbsp", "sugar", "granulated"),
        "\\ingredient{3}{eggs}": (3, None, "eggs", ""),
        "\\ingredient[3]{}{eggs}": (3, None, "eggs", ""),
        "\\ing[3]{}{eggs}": (3, None, "eggs", ""),
        "\\ing{2¼ l}{Wasser}": (2.25, "l", "Wasser", ""),
        "\\ing[2¼]{l}{Wasser}": (2.25, "l", "Wasser", ""),
        "\\ing{2¼ l Wasser}": (2.25, "l", "Wasser", ""),
        "\\Ing{2¼ l Wasser}": (2.25, "l", "Wasser", ""),
        "\\Ingredient{2¼ l Wasser}": (2.25, "l", "Wasser", ""),
        # Not sure if this is ideal:
        "\\ing{etwas}{Chili}": (0, None, "Chili", ""),
    }

    parser = IngredientParser(None, False, ignore_automations=True)

    for key, val in expectations.items():
        match = ing_regex.match(key)
        amount = get_ingredient_amount(parser, match)
        unit = get_ingredient_unit(parser, match)
        food = get_ingredient_food(parser, match)
        note = get_ingredient_note(parser, match)
        print(f"{match} // {amount} // {unit} // {food} // {note}")
        assert (amount, unit, food, note) == val, f"Wrong result when testing {key}"
