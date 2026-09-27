# HW4 AI Prompts

Every prompt I gave the AI assistant (Claude Code) during Homework 4, word for word, grouped by question.

## Setup

1. Hey CC. Let's work on Homework 4, okay? So everything we do rn should go in the hw4 folder
2. There are 13 questions in this hw. Can you make 13 sub folders, one for each question?

## Q1

1. tysm. For Q1. Make AI_prompts.md and update it with all the prompts I give you. It should include all the prompts I give you and under all the questions. Keep it updated as we work

## Q2

1. For Q2, please make output/harness.md and put the following in it: "the catalogue is important because it details the products that our store sells. It's broken out in a way where Campus Customs can organize it and a shopper can tell what the product is. Inventory is important as it lays out how much of everything Campus Customs has, so it knows how much it can sell of each item and each size. Users is important because it outlays the people who shop at Campus Customs, so who CC needs to serve."

## Q3

1. Okay CC, for Q3 we're gonna build a website for Campus Customs. Please use the data in the data_hw_4 and make a website with the following pages: Home, Products, About Us, Log In, Create Account. There should be a nav bar that links to the pages. Don't put anything on the pages yet, just make them pls
2. Write this on Home: 'Custom Official Yale Gear', 'Gear for all Yale Colleges', and 'Get ready to BEAT Harvard'. For About Us: Yale's #1 Stop for Gear. Campus Customs has been serving Yale students and fans since 1975. We have lots of Yale branded gear and merch."
3. Thank you. Now for products, please show product images from the catalogue (use the image paths in the database) and have each product's name and a short description. Each product should open a single-item page with a large image on one side and full product text on the other: description, size, stock. If someone clicks a card they should go straight there. Also add a chat interface in the bottom right. And can you change the colors to blue and white? Godspeed

## Q4

1. Nailed it CC. Let's jump to Q4
2. Let's build the flow for making an account. For Create Account, let's make 'First Name', 'Last Name', 'email', 'password', and 'confirm 'password'. For log in, include email and password. When we get new accounts, add them to the users table. But make sure the data is protected so no human or AI can hack it
3. Can you explain to me how we protect the info the users give us?
4. Thanks. In outputs/harness.md, please write the following: We take their first name, last name, email, and password. That's the minimum information we need to target them, and it's all I want to collect because the less fields there are, the lower our bouncerate will be. #Marketing. We hash the passwords, give no hints, and have limited guessing. We will never send out any information we have stored, and have protection against common types of hacking attached\
5. *attacks
6. Can you make the home page a bit cooler? Like add some suggested products or something?
7. It looks sexy tysm

## Q5

1. Now Q5
2. Let's build the chatbot as a PydanticAI model. Use FastAPI (idk what that means but it's in the directions). Put the app in backend/main.py, which is what I run with Uvicorn. Give it these following powers: backend/prompts/prompt.md, which is the system prompt, backend/agent.py, which is the agent/entry wiring, backendtools.py, which is the tools the agent can call, and backend/models.py, which is the backend structure types. In main.py, make it so the agent can respond to people and help them find stuff. Describe Campus Custom's voice (?) and the safety info you use and put it in prompts/prompt.md. Put chat replies and product cards in models.py. The backend should run from a folder like this: uvicorn main:app --reload --port 8000

## Q6

1. Tysm. For Q6 please give the agent tools it needs to look up information from campus_customs.db. This should be price, product description, sizes, and how much are in stock. Only use the info in the database, do not invent any prices or info, and if an item is out of stock, state that clearly. In prompts/prompt.py, indicate that the tools we're using are called description_lookup, size_lookup, and stock_lookup. In harness/output.ai, say I chose these fields because they are what is relevant to someone who is shopping.

## Q7

1. Sick. Now for Q7, as a user types something into the search bar, please dynamically search the catalogue and display the matching product cards.
2. [Screenshot of the assignment: "Update `prompts/prompt.md` and `output/harness.md` so it is clear how search results reach the page."] What does this mean. Do not do it, just tell me
3. Oh I needed that in a Q7 folder. FOr the prompts/prompt.md, tell the AI that the things it posts will be seen by people looking quickly, so be to the point and highlight the important things. For output/harness, I told the AI agent to use the database and, using the fields I told it to search, bring that information over to the website

## Q8

1. Now Q8 CC
2. Let's save a user's chat history in the database under chat messages. Fill in all the appropriate fields based on the fields that are already in there. Feel free to use any agent to answer any question as long as it doesn't give away any backend or private information. Also log the agents you use. This only needs to be done for logged in users. Also, the chat bot should be able to filter products for them. It can do that by type of clothing, size, color, logo/script on shirt, and warm/cold weather clothing. If it has long sleeves or a hood put it in cold, if not, warm
3. Wow CC, I'm impressed
4. Boola Boola

## Q9

1. Can you make the following improvements: Can you add sorting filters, ie highest to lowest price. Can you add a hover effect that allows users to add something to their cart? In outputs/usability, say "for the front end, I added sorting filters, which will really help the users sort through the options and gives the website the feel of a professional website. I also added a hover feature that allows users to easily add things to their cart. This is more convenient for them and makes them more likely to buy, which is good for campus customs
2. Thanks. Pasuing for now
3. Thanks! Now for the backend, can you make sure that the website will reject orders if the requested quantity of an item exceeds the available stock? And create backend functionality for the shopping cart. Add API endpoints so items can be added/removed/have their quantities updated. In output/usability.md, please say that the rejection is necessary so that we do not oversell and we can fulfill every order we promised, and the second one is needed to improve the reliability of what we made and ensuring totals are calculated consistantly"
4. This is still Q9
5. I split it up

## Q10

1. Thanks CC, on to Q10
2. Alright, let's give it a storefront design feel. Let's make the background give store-vibes, so like i'm looking in through a glass window onto a store. Change the fonts to something more attention-grabby, and give it a hierarchy so there is more emphasis on the important lines. Put some bulldogs on the screen, maybe some of them fighting other Ivy League mascots. The Chat should say Boola Boola instead of hello. Also have a ticker somewhere on the homepage where users can follow the scores of Yale athletics
3. In outputs/design.md, put this. "I make the website prettier with better font and a more store-like layout. I leaned into the Yale athletics connection, and users can look at cool pictures of Bulldogs winning, and even track Yale's performance

## Q11

1. Q11: I'm gonna test some of the stuff we made. Document it in output/app_check.html. I'm gonna send you some screenshots and captions, put them in there
2. Also can I double-click to open that html link you're making?
3. [Screenshot: Products page searching "hoo"] This has the dynamic search results, and if I put it over the size there is an option to add to cart (I can't get it in the ss)
4. Can you add the quantity of each item to somewhere on the website? Quantity is from the database
5. Thanks! Get rid of the screenshot I already sent and I'll send you new ones. Put them in output/app_check_images/ and link them from app_check.html with relative paths
6. [Screenshot: Products page searching "hoo" with the size/stock bar open] Dynamic search and Inventory level
7. [Screenshot: same view, also showing the "in stock" badges on each card] replace that one with this one
8. [Screenshot: Products page sorted by Name: A to Z] Filter from Problem 9

## Q12

1. Thanks CC, time for Q11
2. *Q12
3. keep an append only output/audit_trail.json for agent loop activity. That should be time, name, result and stop reason). Don't wipe it between runs. In prompts/promot.md, make some safety rails. Don't run anything for over 3 mins so we don't overuse tokens, make sure all safety guardrails we put in are in place. Then do all of this: [pasted:] Search/product results: cap at 50 products per request, with 20 products displayed per page. Cart quantity: maximum 10 units of the same product/size per cart. Processing loops: cap loops over products/cart items at 100 iterations before stopping or returning an error. Search/filter requests: return at most 50 matches, even if more products qualify. [end paste] Then finish output/harness.md, making it clear how everything works. List the model fields in models.py, including why we chose them,  the tools and abilities, our safety rules, and spec limits

## Q13

1. [Screenshot: expected file layout for hw4/ and the local-only data/ pack] thanks CC! For Q13, put all our code in a folder named hw4 and push it to a public GitHub repository. DO NOT put my real .env, campus_customs.db, or product images on the GitHub repo. Use .gitignore. Include .env.example with placeholders. Follow the attached file layout. Make sure the agent itself is the four files under backend/ (prompts.prompt, agent, tools, models) and README.md should explain how to run and front and and back end after placing the data pack
