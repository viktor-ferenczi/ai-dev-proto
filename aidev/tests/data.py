import os
from typing import Callable

from aidev.common.util import read_text_file
from aidev.editing.model import Hunk, Document, Block

SCRIPT_DIR = os.path.dirname(__file__)

SOLUTIONS_DIR = os.path.join(SCRIPT_DIR, 'solutions')
HELLO_WORLD_DIR = os.path.join(SOLUTIONS_DIR, 'HelloWorld')
ORIGINAL_SOLUTION_DIR = os.path.join(HELLO_WORLD_DIR, 'original')
OUTPUT_SOLUTION_DIR = os.path.join(HELLO_WORLD_DIR, 'output')


def crop_text(count_tokens: Callable[[str], int], text: str, max_tokens: int, separator: str = '\n\n') -> str:
    assert max_tokens > 0
    paragraphs = []
    total_tokens = 0
    start = 0
    more = True
    while more and total_tokens < max_tokens:
        end = text.find(separator, start)
        if end < 0:
            break

        end += len(separator)
        paragraph = text[start:end]

        paragraph_tokens = count_tokens(paragraph)
        if separator != '. ' and total_tokens + paragraph_tokens > max_tokens:
            paragraph = crop_text(count_tokens, paragraph, max_tokens - total_tokens, '. ')
            paragraph_tokens = count_tokens(paragraph)
            more = False

        if total_tokens + paragraph_tokens > max_tokens:
            break

        paragraphs.append(paragraph)
        total_tokens += paragraph_tokens

        start = end

    result = ''.join(paragraphs)
    assert count_tokens(result) <= max_tokens, (count_tokens(result), max_tokens)
    return result


# This test works only with DeepSeek's tokenizer
# assert crop_text(OpenAIEngine(), 'First. Paragraph.\n\nSecond. Paragraph.\n\nThird. Paragraph.', 14) == 'First. Paragraph.\n\nSecond. '

def load_book() -> str:
    path = os.path.join(SCRIPT_DIR, 'pg18857.txt')
    book = read_text_file(path)
    book = book[book.find('CHAPTER 1\n'):]
    return book


BOOK = load_book()

SYSTEM_CODING_ASSISTANT = '''\
You are a helpful coding assistant experienced in C#, .NET Core., HTML, JavaScript and Python.
'''

INSTRUCTION_DEDUPLICATE_FILES = '''\
Your task is to write a Python 3 function to identify duplicate files in a folder and return a summary of them.

Requirements:
- At any depth in the subdirectory structure.
- Two files are duplicates if they have the same size and contents.
- File contents can be checked based on their SHA256 hashes (checksums).
- Do not read whole files into memory, calculate the hash in 32kB chunks.
- The risk of a hash collision is acceptable in this use case.
- Must find all duplicate files.
- Must NOT delete any files.
- The return value of the function must be a dictionary. The key must be the tuple of (file_size, checksum), values are the list of paths. Returns ONLY the duplicates, where there are at least two files in the list.
- The solution must work on both Windows and UNIX (Linux, MAC).
- Do not calculate the checksum of files with a unique size, because they cannot be duplicates.

Further instructions:
- Add only very concise comments into the code wherever it is absolutely necessary.
- Keep the code in each function short and as simple as possible.
- Avoid deep nesting of flow control.
- Factor the code into separate classes, methods or functions as needed to keep them simple to understand individually.
- Avoid assigning variables which are not used afterwards.
- Structure the code to be very easy to read and understand by humans.
- Add type hints to all function parameters, return values and variables.
- Provide only the code and nothing else.
- You are an expert developer, you can code this simple task very well.
'''

# Questions taken from https://codeburst.io/100-coding-interview-questions-for-programmers-b1cf74885fb7
QUESTIONS = [
    'How is a bubble sort algorithm implemented?',
    'How is a merge sort algorithm implemented?',
    'How do you count the occurrence of a given character in a string?',
    'How do you print the first non-repeated character from a string?',
    'How do you convert a given String into int like the atoi()?',
    'How do you implement a bucket sort algorithm?',
    'How do you implement a counting sort algorithm?',
    'How do you remove duplicates from an array in place?',
    'How do you reverse an array in place in Java?',
    'How are duplicates removed from an array without using any library?',
    'How is a radix sort algorithm implemented?',
    'How do you swap two numbers without using the third variable?',
    'How do you check if two rectangles overlap with each other?',
    'How do you design a vending machine?',
    'How do you find the missing number in a given integer array of 1 to 100?',
    'How do you find the duplicate number on a given integer array?',
    'How do you find duplicate numbers in an array if it contains multiple duplicates?',
    'Difference between a stable and unstable sorting algorithm?',
    'How is an iterative quicksort algorithm implemented?',
    'How do you find the largest and smallest number in an unsorted integer array?',
    'How do you reverse a linked list in place?',
    'How to add an element at the middle of the linked list?',
    'How do you sort a linked list in Java?',
    'How do you find all pairs of an integer array whose sum is equal to a given number?',
    'How do you implement an insertion sort algorithm?',
    'How are duplicates removed from a given array in Java?',
    'how to remove the duplicate character from String?',
    'How to find the maximum occurring character in a given String?',
    'How is an integer array sorted in place using the quicksort algorithm?',
    'How do you reverse a given string in place?',
    'How do you print duplicate characters from a string?',
    'How do you check if two strings are anagrams of each other?',
    'How do you find all the permutations of a string?',
    'How can a given string be reversed using recursion?',
    'How do you check if a given string is a palindrome?',
    'How do you find the length of the longest substring without repeating characters?',
    'Given string str, How do you find the longest palindromic substring in str?',
    'How do you check if a string contains only digits?',
    'How to remove Nth Node from the end of a linked list?',
    'How to merge two sorted linked lists?',
    'How to convert a sorted list to a binary search tree?',
    'How do you find duplicate characters in a given string?',
    'How do you count the number of vowels and consonants in a given string?',
    'How do you reverse words in a given sentence without using any library method?',
    'How do you check if two strings are a rotation of each other?',
    'How to convert a byte array to String?',
    'How do you remove a given character from String?',
    'How do you find the middle element of a singly linked list in one pass?',
    'How do you check if a given linked list contains a cycle? How do you find the starting node of the cycle?',
    'How do you reverse a linked list?',
    'How do you reverse a singly linked list without recursion?',
    'How are duplicate nodes removed in an unsorted linked list?',
    'How do you find the length of a singly linked list?',
    'How do you find the third node from the end in a singly linked list?',
    'How do you find the sum of two linked lists using Stack?',
    'What is the difference between array and linked list?',
    'How to remove duplicates from a sorted linked list?',
    'How to find the node at which the intersection of two singly linked lists begins.',
    'Given a linked list and a value x, partition it such that all nodes less than x come before nodes greater than or equal to x.',
    'How to check if a given linked list is a palindrome?',
    'How to remove all elements from a linked list of integers which matches with given value?',
    'How is a binary search tree implemented?',
    'How do you perform preorder traversal in a given binary tree?',
    'How do you traverse a given binary tree in preorder without recursion?',
    'How do you perform an inorder traversal in a given binary tree?',
    'How do you print all nodes of a given binary tree using inorder traversal without recursion?',
    'How do you implement a postorder traversal algorithm?',
    'How do you traverse a binary tree in postorder traversal without recursion?',
    'How are all leaves of a binary search tree printed?',
    'How do you count a number of leaf nodes in a given binary tree?',
    'How do you perform a binary search in a given array?',
    'How to Swap two numbers without using the third variable?',
    'How to check if two rectangles overlap with each other?',
    'How to design a Vending Machine?',
    'How to implement an LRU Cache in your favorite programming language?',
    'How to check if a given number is a Palindrome?',
    'How to check if a given number is an Armstrong number?',
    'How to find all prime factors of a given number?',
    'How to check if a given number is positive or negative in Java?',
    'How to find the largest prime factor of a given integral number?',
    'How to print all prime numbers up to a given number?',
    'How to print Floyd’s triangle?',
    'How to print Pascal’s triangle?',
    'How to calculate the square root of a given number?',
    'How to check if the given number is a prime number?',
    'How to add two numbers without using the plus operator in Java?',
    'How to check if a given number is even/odd without using the Arithmetic operator?',
    'How to print a given Pyramid structure?',
    'How to find the highest repeating world from a given file in Java?',
    'How to reverse a given Integer in Java?',
    'How to convert a decimal number to binary in Java?',
    'How to check if a given year is a leap year in Java?',
    'Can you implement a Binary search Algorithm without recursion?',
    'Difference between a stable and unstable sorting algorithm?',
    'What is Depth First Search Algorithm for a binary tree?',
    'How is an iterative quicksort algorithm implemented?',
    'How do you implement an insertion sort algorithm?',
    'How is a merge sort algorithm implemented?',
    'What is the difference between Comparison and Non-Comparison Sorting Algorithms?',
    'How do implement Sieve of Eratosthenes Algorithms for Prime Number?',
]

SHOPPING_CART_CS = '''\
using Microsoft.AspNetCore.Http;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace Shop.Data.Models
{
    public class ShoppingCart
    {
        private readonly ApplicationDbContext _context;

        public ShoppingCart(ApplicationDbContext context)
        {
            _context = context;
        }

        public string Id { get; set; }
        public IEnumerable<ShoppingCartItem> ShoppingCartItems { get; set; }

        public static ShoppingCart GetCart(IServiceProvider services)
        {
            //TODO design issue: Data layer referencing web specific details 
            ISession session = services.GetRequiredService<IHttpContextAccessor>()?.HttpContext.Session;
            var context = services.GetService<ApplicationDbContext>();
            string cartId = session.GetString("CartId") ?? Guid.NewGuid().ToString();

            session.SetString("CartId", cartId);
            return new ShoppingCart(context) { Id = cartId };
        }

        //TODO design issue: returning bool, but no additional info if amount is invalid. View decides what error message to show
        //TODO this is supposed to be application- or domain-level logic
        //TODO too much branching
        public bool AddToCart(Food food, int amount)
        {
            if (food.InStock == 0 || amount == 0)
            {
                return false;
            }

            var shoppingCartItem = _context.ShoppingCartItems.SingleOrDefault(
                s => s.Food.Id == food.Id && s.ShoppingCartId == Id);
            var isValidAmount = true;
            if (shoppingCartItem == null)
            {
                if (amount > food.InStock)
                {
                    isValidAmount = false;
                }
                shoppingCartItem = new ShoppingCartItem
                {
                    ShoppingCartId = Id,
                    Food = food,
                    Amount = Math.Min(food.InStock, amount)
                };
                _context.ShoppingCartItems.Add(shoppingCartItem);
            }
            else
            {
                //TODO clean code: complex evaluation as an if predicate. Wrap it in a function
                if (food.InStock - shoppingCartItem.Amount - amount >= 0)
                {
                    shoppingCartItem.Amount += amount;
                }
                else
                {
                    //TODO redundant parenthesis
                    shoppingCartItem.Amount += (food.InStock - shoppingCartItem.Amount);
                    isValidAmount = false;
                }
            }


            _context.SaveChanges();
            return isValidAmount;
        }

        public int RemoveFromCart(Food food)
        {
            var shoppingCartItem = _context.ShoppingCartItems.SingleOrDefault(
                s => s.Food.Id == food.Id && s.ShoppingCartId == Id);
            int localAmount = 0;
            if (shoppingCartItem != null)
            {
                if (shoppingCartItem.Amount > 1)
                {
                    shoppingCartItem.Amount--;
                    localAmount = shoppingCartItem.Amount;
                }
                else
                {
                    _context.ShoppingCartItems.Remove(shoppingCartItem);
                }
            }

            _context.SaveChanges();
            return localAmount;
        }

        public IEnumerable<ShoppingCartItem> GetShoppingCartItems()
        {
            return ShoppingCartItems ??
                   (ShoppingCartItems = _context.ShoppingCartItems.Where(c => c.ShoppingCartId == Id)
                       .Include(s => s.Food));
        }

        public void ClearCart()
        {
            var cartItems = _context
                .ShoppingCartItems
                .Where(cart => cart.ShoppingCartId == Id);

            _context.ShoppingCartItems.RemoveRange(cartItems);
            _context.SaveChanges();
        }

        public decimal GetShoppingCartTotal()
        {
            return _context.ShoppingCartItems.Where(c => c.ShoppingCartId == Id)
                .Select(c => c.Food.Price * c.Amount).ToList().Sum();
        }

    }
}
'''.replace('\r\n', '\n')

ADD_TO_CARD_TODO = r'''
```cs
        //TODO too much branching
        public bool AddToCart(Food food, int amount)
        {
            if (food.InStock == 0 || amount == 0)
            {
                return false;
            }

            var shoppingCartItem = _context.ShoppingCartItems.SingleOrDefault(
                s => s.Food.Id == food.Id && s.ShoppingCartId == Id);
            var isValidAmount = true;
            if (shoppingCartItem == null)
            {
                if (amount > food.InStock)
                {
                    isValidAmount = false;
                }
                shoppingCartItem = new ShoppingCartItem
                {
                    ShoppingCartId = Id,
                    Food = food,
                    Amount = Math.Min(food.InStock, amount)
                };
                _context.ShoppingCartItems.Add(shoppingCartItem);
            }
            else
            {
                if (food.InStock - shoppingCartItem.Amount - amount >= 0)
                {
                    shoppingCartItem.Amount += amount;
                }
                else
                {
                    shoppingCartItem.Amount += (food.InStock - shoppingCartItem.Amount);
                    isValidAmount = false;
                }
            }

            _context.SaveChanges();
            return isValidAmount;
        }

```
'''

ADD_TO_CARD_TODO_RELEVANT_HUNK = Hunk(
    document=Document.from_text(rel_path='ShoppingCart.cs', text=SHOPPING_CART_CS),
    block=Block.from_range(36, 79),
    markers=[
        Block.from_range(62, 63),
        Block.from_range(69, 70),
    ]
)

REGRESSION_DOCUMENT_JSON = r'''{
  "path": "Shop.Data/Seeds/DbInitializer.cs",
  "doctype": "CSHARP",
  "lines": [
    "using Microsoft.AspNetCore.Builder;",
    "using Microsoft.Extensions.DependencyInjection;",
    "using Shop.Data;",
    "using Shop.Data.Models;",
    "using System.Collections.Generic;",
    "using System.Linq;",
    "",
    "namespace Shop.Data.Seeds",
    "{",
    "    public class DbInitializer",
    "    {",
    "        public static void Seed(IApplicationBuilder applicationBuilder)",
    "        {",
    "            using (var serviceScope = applicationBuilder.ApplicationServices.GetRequiredService<IServiceScopeFactory>()",
    "                .CreateScope())",
    "            {",
    "                ApplicationDbContext context = serviceScope.ServiceProvider.GetService<ApplicationDbContext>();",
    "",
    "                context.Database.EnsureCreated();",
    "",
    "                if (!context.Categories.Any())",
    "                {",
    "                    context.Categories.AddRange(Categories.Select(c => c.Value));",
    "                }",
    "",
    "                //context.Drinks.RemoveRange(context.Drinks);",
    "                if (!context.Foods.Any())",
    "                {",
    "                    var foods = new Food[]",
    "                    {",
    "                         new Food",
    "                         {",
    "                             Name = \"Eggplant\",",
    "                             Category = categories[\"Vegetable\"],",
    "                             ImageUrl = \"https://images.pexels.com/photos/321551/pexels-photo-321551.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=450&w=450\",",
    "                             InStock = 20,",
    "                             IsPreferedFood = false,",
    "                             ShortDescription = \"The aubergine (also called eggplant) is a plant. Its fruit is eaten as a vegetable.\",",
    "                             LongDescription = \"The plant is in the nightshade family of plants. It is related to the potato and tomato. Originally it comes from India and Sri Lanka. The Latin/French term aubergine originally derives from the historical city of Vergina (Βεργίνα) in Greece.\",",
    "                             Price = 4.5M",
    "                         },",
    "                        new Food",
    "                        {",
    "                            Name = \"Cauliflower\",",
    "                            Category = categories[\"Vegetable\"],",
    "                            ImageUrl = \"https://images.pexels.com/photos/461245/pexels-photo-461245.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=450&w=450\",",
    "                            InStock = 20,",
    "                            IsPreferedFood = true,",
    "                            ShortDescription = \"Cauliflower is one of several vegetables in the species Brassica oleracea, in the family Brassicaceae.\",",
    "                            LongDescription = \"Cauliflower is a variety of cabbage, whose white flower head is eaten. Cauliflower is very nutritious, and may be eaten cooked, raw or pickled. It is a popular vegetable in Poland where it is eaten in a soup with cream or fried with bread crumbs.\",",
    "                            Price = 5.3M",
    "                        },",
    "                        new Food",
    "                        {",
    "                            Name = \"Broccoli\",",
    "                            Category = categories[\"Vegetable\"],",
    "                            ImageUrl = \"https://images.pexels.com/photos/47347/broccoli-vegetable-food-healthy-47347.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=450&w=450\",",
    "                            InStock = 20,",
    "                            IsPreferedFood = true,",
    "                            ShortDescription = \"Broccoli is a plant, Brassica oleracea. It is a vegetable like cabbage.\",",
    "                            LongDescription = \"Broccoli has green flower heads and a stalk. It comes from Mexico and is one of the most bought vegetables in England.\",",
    "                            Price = 3.3M",
    "                        },",
    "                        new Food",
    "                        {",
    "                            Name = \"Apple\",",
    "                            Category = categories[\"Fruit\"],",
    "                            ImageUrl = \"https://images.pexels.com/photos/39803/pexels-photo-39803.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=450&w=450\",",
    "                            InStock = 20,",
    "                            IsPreferedFood = true,",
    "                            ShortDescription = \"The apple tree (Malus domestica) is a tree that grows fruit (such as apples) in the rose family best known for its juicy, tasty fruit.\",",
    "                            LongDescription = \"Apples are generally propagated by grafting, although wild apples grow readily from seed. Apple trees are large if grown from seed, but small if grafted onto roots (rootstock). There are more than 7,500 known cultivars of apples, with a range of desired characteristics. Different cultivars are bred for various tastes and uses: cooking, eating raw and cider production are the most common uses.\",",
    "                            Price = 2.7M",
    "                        },",
    "                        new Food",
    "                        {",
    "                            Name = \"Avocado\",",
    "                            Category = categories[\"Fruit\"],",
    "                            ImageUrl = \"https://images.pexels.com/photos/557659/pexels-photo-557659.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=450&w=450\",",
    "                            InStock = 20,",
    "                            IsPreferedFood = false,",
    "                            ShortDescription = \"An avocado is a berry fruit. It has medium dark green or dark green bumpy or smooth skin depending on the variety.\",",
    "                            LongDescription = @\"The flesh of an avocado is deep chartreuse green in color near the skin and pale chartreuse green near the core. It has a creamy, rich texture.",
    "        Avocado trees come from Central America and Mexico. They can grow in many places, as long as it is not too cold.\",",
    "                            Price = 6.1M",
    "                        },",
    "                        new Food",
    "                        {",
    "                            Name = \"Banana\",",
    "                            Category = categories[\"Fruit\"],",
    "                            ImageUrl = \"https://images.pexels.com/photos/38283/bananas-fruit-carbohydrates-sweet-38283.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=450&w=450\",",
    "                            InStock = 20,",
    "                            IsPreferedFood = true,",
    "                            ShortDescription = \"A banana is the common name for a type of fruit and also the name for the herbaceous plants that grow it.\",",
    "                            LongDescription = \"It is thought that bananas were grown for food for the first time in Papua New Guinea.[1] Today, they are cultivated in tropical regions around the world.[2] Most banana plants are grown for their fruits, which botanically are a type of berry. Some are grown as ornamental plants, or for their fibres.\",",
    "                            Price = 4.6M",
    "                        },",
    "                        new Food",
    "                        {",
    "                            Name = \"Grapefruit\",",
    "                            Category = categories[\"Fruit\"],",
    "                            ImageUrl = \"https://images.pexels.com/photos/209549/pexels-photo-209549.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=450&w=450\",",
    "                            InStock = 20,",
    "                            IsPreferedFood = false,",
    "                            ShortDescription = \"Grapefruit is a citrus fruit grown in sub-tropical places.\",",
    "                            LongDescription = \"The tree which the grapefruit grows on is normally 5-6 meters tall but can reach up to 15 meters tall. It has dark green leaves that measure up to 150mm and has white flowers that grow 5cm in length.\",",
    "                            Price = 6.4M",
    "                        },",
    "                        new Food",
    "                        {",
    "                            Name = \"Barley\",",
    "                            Category = categories[\"Grain\"],",
    "                            ImageUrl = \"https://images.pexels.com/photos/533346/pexels-photo-533346.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=450&w=450\",",
    "                            InStock = 20,",
    "                            IsPreferedFood = false,",
    "                            ShortDescription = \"Barley, a member of the grass family, is a major cereal grain grown in temperate climates globally.\",",
    "                            LongDescription = \"It was one of the first cultivated grains, particularly in Eurasia as early as 10,000 years ago. Barley has been used as animal fodder, as a source of fermentable material for beer and certain distilled beverages, and as a component of various health foods. It is used in soups and stews, and in barley bread of various cultures. Barley grains are commonly made into malt in a traditional and ancient method of preparation.\",",
    "                            Price = 1.6M",
    "                        },",
    "                        new Food",
    "                        {",
    "                            Name = \"Beef\",",
    "                            Category = categories[\"Meat\"],",
    "                            ImageUrl = \"https://images.pexels.com/photos/618775/pexels-photo-618775.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=450&w=450\",",
    "                            InStock = 20,",
    "                            IsPreferedFood = true,",
    "                            ShortDescription = \"Beef is the culinary name for meat from bovines, especially cattle.\",",
    "                            LongDescription = \"Beef can be harvested from cows, bulls, heifers or steers. Acceptability as a food source varies in different parts of the world.\",",
    "                            Price = 8.8M",
    "                        },",
    "                        new Food",
    "                        {",
    "                            Name = \"Chicken\",",
    "                            Category = categories[\"Meat\"],",
    "                            ImageUrl = \"https://images.pexels.com/photos/616353/pexels-photo-616353.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=450&w=450\",",
    "                            InStock = 20,",
    "                            IsPreferedFood = true,",
    "                            ShortDescription = \"Chicken is the most common type of poultry in the world, and was one of the first domesticated animals.\",",
    "                            LongDescription = \"Chicken is a major worldwide source of meat and eggs for human consumption. It is prepared as food in a wide variety of ways, varying by region and culture. The prevalence of chickens is due to almost the entire chicken being edible, and the ease of raising them.\",",
    "                            Price = 5.3M",
    "                        },",
    "                        new Food",
    "                        {",
    "                            Name = \"Butter\",",
    "                            Category = categories[\"Milk\"],",
    "                            ImageUrl = \"https://images.pexels.com/photos/531334/pexels-photo-531334.jpeg?auto=compress&cs=tinysrgb&dpr=1&w=450\",",
    "                            InStock = 20,",
    "                            IsPreferedFood = false,",
    "                            ShortDescription = \"Butter is a dairy product with high butterfat content which is solid when chilled and at room temperature in some regions, and liquid when warmed.\",",
    "                            LongDescription = \"It is made by churning fresh or fermented cream or milk to separate the butterfat from the buttermilk. It is generally used as a spread on plain or toasted bread products and a condiment on cooked vegetables, as well as in cooking, such as baking, sauce making, and pan frying. Butter consists of butterfat, milk proteins and water, and often added salt.\",",
    "                            Price = 5.0M",
    "                        },",
    "                        new Food",
    "                        {",
    "                            Name = \"Cheese\",",
    "                            Category = categories[\"Milk\"],",
    "                            ImageUrl = \"https://images.pexels.com/photos/821365/pexels-photo-821365.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=450&w=450\",",
    "                            InStock = 20,",
    "                            IsPreferedFood = true,",
    "                            ShortDescription = \"Cheese is a dairy product derived from milk that is produced in a wide range of flavors, textures, and forms by coagulation of the milk protein casein.\",",
    "                            LongDescription = \"It comprises proteins and fat from milk, usually the milk of cows, buffalo, goats, or sheep. During production, the milk is usually acidified, and adding the enzyme rennet causes coagulation. The solids are separated and pressed into final form.\",",
    "                            Price = 4.4M",
    "                        }",
    "                    };",
    "",
    "",
    "                    //foreach (var food in foods)",
    "                    //{",
    "                    //    food.ImageUrl = $\"/images/Foods/{food.Name}.png\";",
    "                    //}",
    "",
    "                    context.AddRange(foods);",
    "                }",
    "",
    "                context.SaveChanges();",
    "            }",
    "        }",
    "",
    "        private static Dictionary<string, Category> categories;",
    "        public static Dictionary<string, Category> Categories",
    "        {",
    "            get",
    "            {",
    "                if (categories == null)",
    "                {",
    "                    var genresList = new Category[]",
    "                    {",
    "                        new Category",
    "                        {",
    "                            Name = \"Vegetable\",",
    "                            Description = \"All vegetables and legumes/beans foods\",",
    "                            ImageUrl = \"https://images.pexels.com/photos/533360/pexels-photo-533360.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=450&w=450\",",
    "                        },",
    "                    new Category",
    "                    {",
    "                        Name = \"Fruit\",",
    "                        Description = \"All fruits\",",
    "                        ImageUrl = \"https://images.pexels.com/photos/8066/fruits-market-colors.jpg?auto=compress&cs=tinysrgb&dpr=1&w=450\"",
    "                    },",
    "                    new Category",
    "                    {",
    "                        Name = \"Grain\",",
    "                        Description = \"Grain (cereal) foods, mostly wholegrain and/or high cereal fibre varieties\",",
    "                        ImageUrl = \"https://images.pexels.com/photos/1537169/pexels-photo-1537169.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=450&w=450\"",
    "                    },",
    "                    new Category",
    "                    {",
    "                        Name = \"Meat\",",
    "                        Description = \"Lean meats and poultry, fish, eggs, tofu, nuts and seeds and legumes/beans\",",
    "                        ImageUrl = \"https://images.pexels.com/photos/65175/pexels-photo-65175.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=450&w=450\"",
    "                    },",
    "                    new Category",
    "                    {",
    "                        Name = \"Milk\",",
    "                        Description = \"Milk, yoghurt cheese and/or alternatives, mostly reduced fat\",",
    "                        ImageUrl = \"https://images.pexels.com/photos/416656/pexels-photo-416656.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=450&w=450\"",
    "                    }",
    "                    };",
    "",
    "                    categories = new Dictionary<string, Category>();",
    "",
    "                    foreach (Category genre in genresList)",
    "                    {",
    "                        //genre.ImageUrl = $\"/images/Categories/{genre.Name}.png\";",
    "                        categories.Add(genre.Name, genre);",
    "                    }",
    "                }",
    "",
    "                return categories;",
    "            }",
    "        }",
    "    }",
    "}"
  ]
}'''

REGRESSION_COMPLETION = r'''```cs
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.DependencyInjection;
using Shop.Data;
using Shop.Data.Models;
using System.Collections.Generic;
using System.Linq;

namespace Shop.Data.Seeds
{
    public class DbInitializer
    {
        public static void Seed(IApplicationBuilder applicationBuilder)
        {
            using (var serviceScope = applicationBuilder.ApplicationServices.GetRequiredService<IServiceScopeFactory>()
                .CreateScope())
            {
                ApplicationDbContext context = serviceScope.ServiceProvider.GetService<ApplicationDbContext>();

                context.Database.EnsureCreated();

                if (!context.Categories.Any())
                {
                    context.Categories.AddRange(Categories.Select(c => c.Value));
                }

                if (!context.Foods.Any())
                {
                    var foods = new Food[]
                    {
                        //genre.ImageUrl = $"/images/Categories/{genre.Name}.png";
                        categories.Add(genre.Name, genre);
                    }

                return categories;
            }
        }
    }
}
```
'''
