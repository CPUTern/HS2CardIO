# HS2CharaCardIO
A Script For HS2 Card IO 

```python
from CardIO import *

card = Card()
#load card
card.load_card(card_load_path)

#read card data
card.data['参数名称'].get_value()

#write card data
card.data['参数名称'].set_value(100)

#save card
card.save_card(card_save_path)

```
