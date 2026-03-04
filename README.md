# HotkeyTagger
This is a hackathon project to manually classify images faster and easier.
This project was built for a short 3 hour hackathon run by [c0mpiled and the Penn State Builder's Collective](https://luma.com/xgtu3nbn?tk=0tpBa4) on February 27, 2026.

Simply run HotkeyTagger.py, and point it at a folder of images to get started. 
The hotkeys are customizable, and the classifications are saved in a csv file in the same folder as the images. 
You should be able to add keybindings at anytime without the csv breaking, and the purpose of the program is to more quickly and easily classify images for later use in supervised machine learning. 
The project is built in python, making use of pyQT5 for the GUI.

A brief (rushed, due to time constraints) demo: https://www.youtube.com/watch?v=62CccaczzBQ
A brief slidedeck overviewing the project and its features: https://pennstateoffice365-my.sharepoint.com/:p:/g/personal/jad507_psu_edu/IQBQE9y4SEuzTJRWDDnQN1taAfqEADTHDavQ7fp_GkdA6D0?e=zjhQbf

You can run datasetDL.py to download the datasets used in the demo to your local machine for testing.

Before the hackathon, while looking for potential teammates, I posted the following synopsis of the project: 

>I'm Jeffrey, in Astronomy and Astrophysics
>
>I want to make a tool that makes it easier to hand-classify a portion of an image set, so that you can train on that portion and have the machine do the rest. I'm planning to use python and a pyQT gui that will load up the image, and you can bind classifications to each keystroke.
>
>For test data, I am thinking of using the handwritten digit dataset from scikit-learn https://scikit-learn.org/1.5/auto_examples/datasets/plot_digits_last_image.html#sphx-glr-auto-examples-datasets-plot-digits-last-image-py (hotkeys would be either 1-0, or have 5678 bound to qwer), and the Olivetti Faces dataset https://scikit-learn.org/1.5/datasets/real_world.html#olivetti-faces-dataset (hotkeys for glasses, mustache, beard, etc)
>
>A major feature I'd like to make sure gets finished is that the hotkey settings are saveable, so that you can work on hand-classifying for a few hours, shut down, and then pick up right where you left off.
> 
> A major question I haven't figured out yet is "what's the best format to save the classifications?" and I can imagine it being easy to just shove it into a csv or json, or maybe i'll finally mess around with postgreSQL or something. It might also make sense to use metadata attached to the image, but I don't really understand how platform-compatible that is.
>
>I haven't done a hackathon before, so I'm not sure how people successfully split the work under such tight time constraints, but if anyone's interested in joining me, I'd be happy to work with them. 

Ultimately, it remained a solo proejct, and was made with the help of Github Copilot and Microsoft Copilot. 
Part of the inspiration for the project was League of Legends, which standardized hotkey bindings to the qwer keys, compared to its predecessor, DotA.
I did not win any prizes during this hackathon, but I hope that this project can be of use to others (and I will definitely be using it, and may work on further improvements).
I believe it to be platform agnostic, due to the use of Path, but have not tested it on anything except my local Windows machine.
Event summary, with links to other teams and projects: https://www.compiled.sh/articles/c0mpiled-6-ai-for-productivity-research
