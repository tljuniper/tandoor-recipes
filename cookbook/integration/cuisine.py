import re

from contextlib import suppress

from cookbook.helper.image_processing import get_filetype
from cookbook.integration.integration import Integration
from cookbook.serializer import RecipeExportSerializer
from cookbook.helper.recipe_url_import import (
    parse_servings,
    parse_servings_text,
    parse_time,
)

from cookbook.helper.ingredient_parser import IngredientParser
from cookbook.models import Ingredient, Recipe, Step

# Regex for capturing the header components of the recipe
# ?: makes a group non-capturing
# \\begin\{recipe\}\s*(?:\[(?P<label>[\w-]*?)\])?\s*\{(?P<title>[\w -]*)\}\s*\{(?P<servings>[\w -]*)\}\s*\{(?P<time>[\w -]*)\}(?P<content>.*?)\\end\{recipe\}
# Example: \begin{recipe} [myLabel] {Lasagna} {4 persons} {30 minutes + 1 hour baking time} the content \end{recipe}
_reg = r"\\begin{recipe}"
_reg += r"\s*"
_reg += r"(?:\[(?P<label>[\w-]*?)\])?"
_reg += r"\s*"
_reg += r"{(?P<title>[^{}]*)}"
_reg += r"\s*"
_reg += r"{(?P<servings>[^{}]*)}"
_reg += r"\s*"
_reg += r"{(?P<time>[^{}]*)}"
_reg += r"(?P<content>.*?)"
_reg += r"\\end{recipe}"
# Flags: dotall and unicode
recipe_regex = re.compile(_reg, re.DOTALL | re.U)

# Regex for capturing ingredients within the recipe
# Amount can either be "amount + unit" or just the unit, if number is specified in []
# We're a little more flexible than the latex version by allowing \ing{3 l water}
_ing = r"\\[Ii]ng(?:redient)?"
_ing += r"(?:\[(?P<number>[^\]]*)\])?"
_ing += r"(?:{(?P<amount>[^{}]*)})?"
_ing += r"{(?P<ing>[^{}]*)}"
ing_regex = re.compile(_ing, re.S | re.U)


def clean_title(title):
    # Clean up LaTeX artifacts in title
    title = re.sub(r"([^\\]*)\\.*", r"\1", title)
    title = re.sub(r"\"=", r"-", title)
    return title.strip()


def get_ingredient_amount(ingredient_parser, match):
    """
    Extract only the amount from the regex match, returning 0 when it can't be parsed
    """
    amount = 0

    if match.group("number"):
        # \ing[3]{l}{milk}
        with suppress(Exception):
            # We still need to run the parser_amount to resolve fractions and handle unicode
            amount, _, _ = ingredient_parser.parse_amount(match.group("number"))
    elif match.group("amount"):
        # \ing{3 l}{milk}
        with suppress(Exception):
            amount, _, _ = ingredient_parser.parse_amount(match.group("amount"))
    else:
        # \ing{3 l milk}
        with suppress(Exception):
            amount, _, _, _ = ingredient_parser.parse(match.group("ing"))

    return amount


def get_ingredient_unit(ingredient_parser, match):
    """
    Extract only the unit from the regex match, returning None when it can't be parsed
    """
    unit = None

    if match.group("number"):
        # \ing[3]{l}{milk}
        with suppress(Exception):
            unit = match.group("amount")
    elif match.group("amount"):
        # \ing{3 l}{milk}
        with suppress(Exception):
            _, unit, _ = ingredient_parser.parse_amount(match.group("amount"))
    else:
        # \ing{3 l milk}
        with suppress(Exception):
            _, unit, _, _ = ingredient_parser.parse(match.group("ing"))

    if unit:
        unit = unit.strip()
    if unit == "":
        unit = None

    return unit


def get_ingredient_food(ingredient_parser, match):
    """
    Extract only the food from the regex match, returning "" when it can't be parsed
    """
    food = ""
    with suppress(Exception):
        _, _, food, _ = ingredient_parser.parse(match.group("ing"))
    return food


def get_ingredient_note(ingredient_parser, match):
    """
    Extract only the note from the regex match, returning "" when it can't be parsed
    """
    note = ""
    with suppress(Exception):
        _, _, _, note = ingredient_parser.parse(match.group("ing"))
    return note


class Cuisine(Integration):
    def get_recipe_from_file(self, file):
        """
        :param file: String containing a single cuisine recipe
        :return: Recipe object
        """
        r = recipe_regex.search(file)
        if not r:
            raise ValueError("Failed to parse recipe")

        title = clean_title(r.group("title"))

        recipe = Recipe.objects.create(
            name=title.strip(),
            created_by=self.request.user,
            internal=True,
            space=self.request.space,
        )

        recipe.servings = parse_servings(r.group("servings"))
        recipe.servings_text = parse_servings_text(r.group("servings"))
        recipe.working_time = parse_time(r.group("time"))

        recipe.save()

        content = r.group("content")
        self._parse_content(recipe, content)

        return recipe

    def split_recipe_file(self, file):
        """
        Takes a file that contains multiple recipes and splits it into a list of cuisine strings
        :param file: ByteIO or any file like object, depends on provider
        :return: list of strings
        """

        # Regex for capturing the beginning and end of the recipe
        _reg = r"\\begin\{recipe\}.*?\\end\{recipe\}"
        recipe_regex = re.compile(_reg, re.DOTALL)

        recipes = []
        recipes.extend(recipe_regex.findall(file))

        return recipes

    def _parse_content(self, recipe, content):
        """
        Parse the contents of the recipe (instructions + ingredients)
        """
        # For now: Create a single step
        # TODO: Split into different steps?

        # Remove ingredients from text
        instruction_text = re.sub(ing_regex, "", content)
        # TODO: Remove redundant \n from instructions, string.strip()
        step = Step.objects.create(
            instruction=instruction_text,
            space=self.request.space,
        )

        ingredient_parser = IngredientParser(self.request, True)

        for match in ing_regex.finditer(content):
            amount = get_ingredient_amount(ingredient_parser, match)
            unit = get_ingredient_unit(ingredient_parser, match)
            food = get_ingredient_food(ingredient_parser, match)
            note = get_ingredient_note(ingredient_parser, match)

            f = ingredient_parser.get_food(food)
            u = ingredient_parser.get_unit(unit)

            step.ingredients.add(
                Ingredient.objects.create(
                    food=f,
                    unit=u,
                    amount=amount,
                    note=note,
                    original_text=match.string,
                    space=self.request.space,
                )
            )

        recipe.steps.add(step)
