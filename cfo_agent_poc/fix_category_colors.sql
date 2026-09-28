-- 一次性订正：把已有库里内置分类的颜色换成按主题分组的新配色。
--
-- 为什么要手动跑：category_catalog 的默认数据用 insert or ignore 写入，
-- 已存在的行不会被覆盖，所以只部署新代码，老库里的分类颜色不会变。
--
-- 只改「仍是旧默认色」的内置分类：人工改过颜色的分类、自定义分类都不动；
-- 只碰 category_catalog.color_token，不涉及交易数据；重复执行无副作用。
--
-- 用法（在仓库根目录）：
--   sqlite3 cfo_agent_poc/data/cfo.sqlite ".backup 'cfo_agent_poc/data/backups/cfo_before_color_fix.sqlite'"
--   sqlite3 cfo_agent_poc/data/cfo.sqlite < cfo_agent_poc/fix_category_colors.sql
-- 刷新页面即可看到新配色，不需要重启服务。

begin;
update category_catalog set color_token = 'cat-2' where id = 'coffee_tea' and color_token = 'cat-1';
update category_catalog set color_token = 'cat-10' where id = 'food_delivery' and color_token = 'cat-2';
update category_catalog set color_token = 'cat-9' where id = 'parking' and color_token = 'cat-3';
update category_catalog set color_token = 'cat-12' where id = 'car_charging' and color_token = 'cat-4';
update category_catalog set color_token = 'cat-16' where id = 'auto' and color_token = 'cat-5';
update category_catalog set color_token = 'cat-11' where id = 'groceries' and color_token = 'cat-6';
update category_catalog set color_token = 'cat-3' where id = 'fruit' and color_token = 'cat-7';
update category_catalog set color_token = 'cat-17' where id = 'bakery' and color_token = 'cat-1';
update category_catalog set color_token = 'cat-14' where id = 'education' and color_token = 'cat-2';
update category_catalog set color_token = 'cat-21' where id = 'books' and color_token = 'cat-3';
update category_catalog set color_token = 'cat-20' where id = 'ecommerce' and color_token = 'cat-4';
update category_catalog set color_token = 'cat-1' where id = 'transport' and color_token = 'cat-5';
update category_catalog set color_token = 'cat-3' where id = 'healthcare' and color_token = 'cat-6';
update category_catalog set color_token = 'cat-6' where id = 'investment' and color_token = 'cat-7';
update category_catalog set color_token = 'cat-19' where id = 'property' and color_token = 'cat-1';
update category_catalog set color_token = 'cat-9' where id = 'telecom' and color_token = 'cat-2';
update category_catalog set color_token = 'cat-7' where id = 'entertainment' and color_token = 'cat-3';
update category_catalog set color_token = 'cat-14' where id = 'credit_repayment' and color_token = 'cat-4';
update category_catalog set color_token = 'cat-4' where id = 'utilities' and color_token = 'cat-5';
update category_catalog set color_token = 'cat-11' where id = 'stationery' and color_token = 'cat-6';
update category_catalog set color_token = 'cat-16' where id = 'digital_services' and color_token = 'cat-7';
update category_catalog set color_token = 'cat-18' where id = 'general_shopping' and color_token = 'cat-1';
update category_catalog set color_token = 'cat-15' where id = 'leisure_travel' and color_token = 'cat-2';
update category_catalog set color_token = 'cat-7' where id = 'lottery' and color_token = 'cat-3';
update category_catalog set color_token = 'cat-21' where id = 'personal_transfer' and color_token = 'cat-4';
update category_catalog set color_token = 'cat-20' where id = 'pet' and color_token = 'cat-6';
update category_catalog set color_token = 'cat-13' where id = 'beauty' and color_token = 'cat-7';
update category_catalog set color_token = 'cat-12' where id = 'furniture_home' and color_token = 'cat-1';
update category_catalog set color_token = 'cat-13' where id = 'maternal_child' and color_token = 'cat-2';
commit;
