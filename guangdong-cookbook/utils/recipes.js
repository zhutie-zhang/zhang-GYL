(function (root, factory) {
  if (typeof module !== 'undefined' && module.exports) module.exports = factory();
  else root.RECIPES = factory();
})(this, function () {
  // 营养成分按"1人份"估算；ingredients.g 用于采购清单分组
  var R = [
    // ---------- 荤菜 ----------
    { id: 'baqieji', name: '白切鸡', kind: '白灼', group: '荤菜', style: '广府', difficulty: 2, time: 35,
      tags: ['清淡', '高蛋白', '宴客'], veto: [], veg: false, occa: false,
      ingredients: [
        { n: '三黄鸡', g: 200, gr: '肉' }, { n: '姜', g: 10, gr: '调味' }, { n: '小葱', g: 10, gr: '调味' },
        { n: '沙姜（可选）', g: 5, gr: '调味' }, { n: '花生油', g: 5, gr: '油' }
      ],
      steps: ['鸡洗净冷水下锅，放姜葱，煮开转小火浸 13 分钟，关火再焖 8 分钟', '捞出立刻泡冰水 10 分钟，皮滑肉嫩', '斩件码盘，姜葱蓉加盐烧热油做成蘸料'],
      nutrition: { kcal: 330, protein: 32, fat: 22, carb: 1, fiber: 0, sodium: 420, vegGram: 0 },
      tip: '白切鸡的脂肪主要在皮，去皮食用更健康；蘸料少盐更佳。' },

    { id: 'yanjuji', name: '盐焗鸡', kind: '小炒', group: '荤菜', style: '客家', difficulty: 1, time: 50,
      tags: ['香口', '高蛋白'], veto: [], veg: false, occa: false,
      ingredients: [
        { n: '三黄鸡', g: 200, gr: '肉' }, { n: '盐焗鸡粉', g: 10, gr: '调味' }, { n: '姜', g: 10, gr: '调味' },
        { n: '葱', g: 10, gr: '调味' }, { n: '料酒', g: 10, gr: '调味' }
      ],
      steps: ['鸡擦干水分，抹盐焗鸡粉（用三分之二量）腌 30 分钟', '姜葱垫电饭锅底，放鸡按下煮饭键焗 25 分钟', '取出斩件，鸡汁可淋回'],
      nutrition: { kcal: 340, protein: 30, fat: 24, carb: 2, fiber: 0, sodium: 950, vegGram: 0 },
      tip: '盐焗粉钠较高，腌料减量、蘸汁少盐；高血压人群每月 1~2 次即可。' },

    { id: 'chashao', name: '蜜汁叉烧', kind: '小炒', group: '荤菜', style: '广府', difficulty: 1, time: 45,
      tags: ['家常', '下饭'], veto: [], veg: false, occa: true,
      ingredients: [
        { n: '梅花肉', g: 150, gr: '肉' }, { n: '叉烧酱', g: 20, gr: '调味' }, { n: '生抽', g: 5, gr: '调味' },
        { n: '料酒', g: 5, gr: '调味' }, { n: '蜂蜜', g: 8, gr: '调味' }, { n: '蒜', g: 5, gr: '调味' }
      ],
      steps: ['梅花肉切条，用叉烧酱、生抽、料酒、蒜腌 30 分钟', '平底锅煎上色后加水焖熟，或烤箱 200 度 25 分钟', '刷蜂蜜回锅 1 分钟，切片'],
      nutrition: { kcal: 330, protein: 20, fat: 20, carb: 16, fiber: 0, sodium: 850, vegGram: 0 },
      tip: '叉烧酱含糖盐较高，一个月吃 1~2 次解馋就好，配青菜同餐更均衡。' },

    { id: 'chizhi', name: '豉汁蒸排骨', kind: '清蒸', group: '荤菜', style: '广府', difficulty: 1, time: 40,
      tags: ['下饭', '快手'], veto: [], veg: false, occa: false,
      ingredients: [
        { n: '肋排', g: 200, gr: '肉' }, { n: '阳江豆豉', g: 8, gr: '调味' }, { n: '蒜', g: 8, gr: '调味' },
        { n: '蚝油', g: 5, gr: '调味' }, { n: '生抽', g: 5, gr: '调味' }, { n: '白糖', g: 3, gr: '调味' },
        { n: '生粉', g: 5, gr: '调味' }
      ],
      steps: ['排骨斩小件，泡水 10 分钟去血水沥干', '豆豉蒜末爆香，与蚝油生抽糖生粉调成腌料拌入排骨腌 20 分钟', '大火蒸 20 分钟，撒葱花'],
      nutrition: { kcal: 380, protein: 24, fat: 28, carb: 6, fiber: 1, sodium: 900, vegGram: 0 },
      tip: '排骨肥瘦各半，蒸前焯一下去浮油；控油可挑精瘦肋排。' },

    { id: 'qingzhengluyu', name: '清蒸鲈鱼', kind: '清蒸', group: '荤菜', style: '顺德', difficulty: 1, time: 20,
      tags: ['清淡', '高蛋白', '老人适宜'], veto: ['seafood'], veg: false, occa: false,
      ingredients: [
        { n: '鲈鱼', g: 300, gr: '水产' }, { n: '姜', g: 10, gr: '调味' }, { n: '葱', g: 10, gr: '调味' },
        { n: '蒸鱼豉油', g: 15, gr: '调味' }, { n: '花生油', g: 5, gr: '油' }, { n: '料酒', g: 5, gr: '调味' }
      ],
      steps: ['鱼去鳞去内脏，两面抹料酒放姜片', '水烧开大火蒸 8 分钟，倒掉盘中汁水蒸汽', '铺葱丝，淋热油和蒸鱼豉油'],
      nutrition: { kcal: 230, protein: 36, fat: 9, carb: 2, fiber: 0, sodium: 780, vegGram: 0 },
      tip: '蒸鱼时间宁短勿长，鱼肉鲜嫩营养流失少；高血压可用无盐蒸鱼汁。' },

    { id: 'baizhuojiweixia', name: '白灼基围虾', kind: '白灼', group: '荤菜', style: '广府', difficulty: 1, time: 10,
      tags: ['清淡', '高蛋白低脂', '快手'], veto: ['seafood'], veg: false, occa: false,
      ingredients: [
        { n: '基围虾', g: 200, gr: '水产' }, { n: '姜', g: 10, gr: '调味' }, { n: '葱', g: 10, gr: '调味' },
        { n: '料酒', g: 10, gr: '调味' }
      ],
      steps: ['虾剪须开背去虾线', '水开下姜葱料酒，放虾煮 2 分钟', '捞出泡冰水，壳肉好分离'],
      nutrition: { kcal: 190, protein: 38, fat: 2, carb: 2, fiber: 0, sodium: 480, vegGram: 0 },
      tip: '高蛋白低脂肪，蘸料用少盐姜葱汁，是最推荐的水产吃法。' },

    { id: 'huadanxiaren', name: '滑蛋虾仁', kind: '小炒', group: '荤菜', style: '广府', difficulty: 2, time: 15,
      tags: ['快手', '下饭'], veto: ['seafood'], veg: false, occa: false,
      ingredients: [
        { n: '虾仁', g: 100, gr: '水产' }, { n: '鸡蛋', g: 150, gr: '蛋' }, { n: '牛奶', g: 30, gr: '奶' },
        { n: '盐', g: 2, gr: '调味' }, { n: '生粉', g: 5, gr: '调味' }, { n: '油', g: 8, gr: '油' }
      ],
      steps: ['虾仁用盐生粉腌 5 分钟', '鸡蛋加牛奶盐打散', '温油滑熟虾仁，倒入蛋液小火推至半凝固即出锅'],
      nutrition: { kcal: 320, protein: 27, fat: 21, carb: 3, fiber: 0, sodium: 620, vegGram: 0 },
      tip: '加牛奶更嫩滑；少油慢推，蛋别炒老。' },

    { id: 'fanqieniurou', name: '番茄炒牛肉', kind: '小炒', group: '荤菜', style: '广府', difficulty: 1, time: 20,
      tags: ['下饭', '高铁'], veto: ['beef'], veg: false, occa: false,
      ingredients: [
        { n: '牛里脊', g: 120, gr: '肉' }, { n: '番茄', g: 250, gr: '菜' }, { n: '姜', g: 5, gr: '调味' },
        { n: '白糖', g: 3, gr: '调味' }, { n: '生抽', g: 5, gr: '调味' }, { n: '生粉', g: 5, gr: '调味' }, { n: '油', g: 8, gr: '油' }
      ],
      steps: ['牛肉切片逆纹腌 15 分钟', '番茄切块炒出沙，加少量水', '下牛肉滑炒至变色，调味收汁'],
      nutrition: { kcal: 240, protein: 22, fat: 12, carb: 10, fiber: 2, sodium: 560, vegGram: 250 },
      tip: '牛肉补铁，番茄富含维生素 C 助吸收；少油少糖依然酸甜开胃。' },

    { id: 'qingjiaoniurou', name: '青椒炒牛肉', kind: '小炒', group: '荤菜', style: '广府', difficulty: 1, time: 20,
      tags: ['下饭', '高铁'], veto: ['beef'], veg: false, occa: false,
      ingredients: [
        { n: '牛里脊', g: 120, gr: '肉' }, { n: '青椒', g: 150, gr: '菜' }, { n: '蒜', g: 5, gr: '调味' },
        { n: '蚝油', g: 5, gr: '调味' }, { n: '生抽', g: 5, gr: '调味' }, { n: '生粉', g: 5, gr: '调味' }, { n: '油', g: 8, gr: '油' }
      ],
      steps: ['牛肉切片腌 15 分钟', '猛火快炒牛肉至变色先盛起', '爆蒜炒青椒，回锅牛肉调味'],
      nutrition: { kcal: 250, protein: 21, fat: 13, carb: 8, fiber: 2, sodium: 640, vegGram: 150 },
      tip: '青椒维 C 丰富，牛肉补铁；猛火快炒保留口感。' },

    { id: 'xianggu_sj', name: '香菇蒸滑鸡', kind: '清蒸', group: '荤菜', style: '广府', difficulty: 1, time: 30,
      tags: ['清淡', '老人适宜'], veto: [], veg: false, occa: false,
      ingredients: [
        { n: '鸡腿肉', g: 180, gr: '肉' }, { n: '香菇', g: 50, gr: '干' }, { n: '姜', g: 8, gr: '调味' },
        { n: '生抽', g: 5, gr: '调味' }, { n: '生粉', g: 5, gr: '调味' }, { n: '油', g: 5, gr: '油' }
      ],
      steps: ['鸡腿肉斩小块，香菇泡发切片', '加姜丝、生抽、生粉抓匀腌 15 分钟', '大火蒸 20 分钟，出锅撒葱花'],
      nutrition: { kcal: 300, protein: 26, fat: 18, carb: 4, fiber: 1, sodium: 640, vegGram: 50 },
      tip: '蒸比炒更少油，肉嫩易嚼，适合老人小孩。' },

    { id: 'gulurou', name: '咕噜肉', kind: '小炒', group: '荤菜', style: '广府', difficulty: 3, time: 40,
      tags: ['宴客', '酸甜'], veto: [], veg: false, occa: true,
      ingredients: [
        { n: '猪里脊', g: 150, gr: '肉' }, { n: '青椒', g: 50, gr: '菜' }, { n: '菠萝', g: 60, gr: '果' },
        { n: '番茄酱', g: 15, gr: '调味' }, { n: '白醋', g: 5, gr: '调味' }, { n: '白糖', g: 10, gr: '调味' },
        { n: '鸡蛋', g: 50, gr: '蛋' }, { n: '淀粉', g: 20, gr: '调味' }, { n: '油', g: 15, gr: '油' }
      ],
      steps: ['里脊切块盐腌，裹蛋液淀粉', '五六成油温炸至金黄捞出', '糖醋汁炒浓，下肉块青椒菠萝翻匀'],
      nutrition: { kcal: 460, protein: 20, fat: 25, carb: 38, fiber: 2, sodium: 700, vegGram: 50 },
      tip: '油炸热量高，油温太高还易产生有害物；建议偶尔吃或改用空气炸锅。' },

    { id: 'kejianiang', name: '客家酿豆腐', kind: '小炒', group: '荤菜', style: '客家', difficulty: 2, time: 35,
      tags: ['高蛋白', '含钙'], veto: [], veg: false, occa: false,
      ingredients: [
        { n: '北豆腐', g: 300, gr: '豆' }, { n: '猪肉末', g: 80, gr: '肉' }, { n: '香菇', g: 20, gr: '干' },
        { n: '小葱', g: 5, gr: '调味' }, { n: '生抽', g: 5, gr: '调味' }, { n: '生粉', g: 5, gr: '调味' }, { n: '油', g: 8, gr: '油' }
      ],
      steps: ['豆腐切块挖小洞，肉末香菇调味酿入', '肉面朝下煎至金黄', '加水焖 5 分钟，勾薄芡撒葱'],
      nutrition: { kcal: 300, protein: 26, fat: 16, carb: 12, fiber: 2, sodium: 700, vegGram: 20 },
      tip: '豆腐优质蛋白加钙，肉末少量点缀即可，很下饭。' },

    // ---------- 素菜 ----------
    { id: 'baizhuocaixin', name: '白灼菜心', kind: '白灼', group: '素菜', style: '广府', difficulty: 1, time: 8,
      tags: ['清淡', '高纤维', '深色蔬菜'], veto: [], veg: true, occa: false,
      ingredients: [
        { n: '菜心', g: 250, gr: '菜' }, { n: '姜丝', g: 5, gr: '调味' },
        { n: '蒸鱼豉油', g: 10, gr: '调味' }, { n: '花生油', g: 5, gr: '油' }
      ],
      steps: ['菜心洗净去老根', '水开加少许油盐，焯 1 分半捞出', '淋豉油，浇一点热油'],
      nutrition: { kcal: 90, protein: 6, fat: 4, carb: 9, fiber: 3, sodium: 600, vegGram: 250 },
      tip: '菜心是"深色蔬菜"，每餐来一份就对了；焯水少油最健康。' },

    { id: 'suanjielan', name: '蒜蓉炒芥兰', kind: '素菜', group: '素菜', style: '广府', difficulty: 1, time: 10,
      tags: ['高纤维', '深色蔬菜'], veto: [], veg: true, occa: false,
      ingredients: [
        { n: '芥兰', g: 250, gr: '菜' }, { n: '蒜', g: 10, gr: '调味' },
        { n: '蚝油', g: 5, gr: '调味' }, { n: '料酒', g: 5, gr: '调味' }, { n: '油', g: 8, gr: '油' }
      ],
      steps: ['芥兰去老茎、斜切，先焯水 1 分钟', '爆香蒜末，大火快炒', '加蚝油料酒调匀即可'],
      nutrition: { kcal: 110, protein: 6, fat: 5, carb: 12, fiber: 4, sodium: 520, vegGram: 250 },
      tip: '芥兰含丰富维生素 C 和钙，焯水去涩后再炒更清爽。' },

    { id: 'haoyoushengcai', name: '蚝油生菜', kind: '素菜', group: '素菜', style: '广府', difficulty: 1, time: 8,
      tags: ['快手', '高纤维'], veto: [], veg: true, occa: false,
      ingredients: [
        { n: '生菜', g: 250, gr: '菜' }, { n: '蚝油', g: 10, gr: '调味' },
        { n: '蒜', g: 5, gr: '调味' }, { n: '白糖', g: 2, gr: '调味' }, { n: '油', g: 5, gr: '油' }
      ],
      steps: ['生菜洗净，水开烫 10 秒捞出', '蒜末、蚝油、糖加少许水煮成汁', '淋在生菜上'],
      nutrition: { kcal: 80, protein: 4, fat: 4, carb: 8, fiber: 2, sodium: 640, vegGram: 250 },
      tip: '烫 10 秒口感最脆，蚝油已有咸味不再加盐。' },

    { id: 'shangtang_ww', name: '上汤娃娃菜', kind: '炖汤', group: '素菜', style: '广府', difficulty: 1, time: 15,
      tags: ['清淡'], veto: [], veg: true, occa: false,
      ingredients: [
        { n: '娃娃菜', g: 300, gr: '菜' }, { n: '皮蛋', g: 30, gr: '蛋' }, { n: '咸蛋', g: 15, gr: '蛋' },
        { n: '蒜', g: 8, gr: '调味' }, { n: '枸杞', g: 3, gr: '干' }, { n: '油', g: 5, gr: '油' }
      ],
      steps: ['娃娃菜切条，蒜瓣煎香', '加高汤或清水煮开，放娃娃菜、皮蛋咸蛋丁', '焖至菜软撒枸杞'],
      nutrition: { kcal: 120, protein: 8, fat: 6, carb: 10, fiber: 2, sodium: 750, vegGram: 300 },
      tip: '皮蛋咸蛋自带咸味，汤里别再放盐；咸蛋可减半。' },

    { id: 'liangguajd', name: '凉瓜煎蛋', kind: '素菜', group: '素菜', style: '广府', difficulty: 1, time: 15,
      tags: ['清热'], veto: [], veg: true, occa: false,
      ingredients: [
        { n: '苦瓜', g: 200, gr: '菜' }, { n: '鸡蛋', g: 150, gr: '蛋' },
        { n: '盐', g: 2, gr: '调味' }, { n: '油', g: 10, gr: '油' }
      ],
      steps: ['苦瓜去瓤切薄片，焯水去苦', '与蛋液、盐拌匀', '少油煎至两面金黄'],
      nutrition: { kcal: 260, protein: 18, fat: 18, carb: 8, fiber: 3, sodium: 380, vegGram: 200 },
      tip: '广东人称苦瓜为凉瓜，清热解暑；焯水去苦后少油煎。' },

    { id: 'jiucaichaodan', name: '韭菜炒蛋', kind: '素菜', group: '素菜', style: '广府', difficulty: 1, time: 10,
      tags: ['快手', '高蛋白'], veto: [], veg: true, occa: false,
      ingredients: [
        { n: '韭菜', g: 150, gr: '菜' }, { n: '鸡蛋', g: 150, gr: '蛋' },
        { n: '盐', g: 2, gr: '调味' }, { n: '油', g: 10, gr: '油' }
      ],
      steps: ['韭菜切段，鸡蛋打散', '温油先滑熟鸡蛋盛起', '快炒韭菜，回蛋调味'],
      nutrition: { kcal: 230, protein: 16, fat: 16, carb: 7, fiber: 2, sodium: 400, vegGram: 150 },
      tip: '韭菜含膳食纤维与维 C，鸡蛋补充蛋白，五分钟搞定。' },

    { id: 'douchilingyu', name: '豆豉鲮鱼油麦菜', kind: '素菜', group: '素菜', style: '广府', difficulty: 1, time: 10,
      tags: ['快手', '下饭'], veto: ['seafood'], veg: false, occa: false,
      ingredients: [
        { n: '油麦菜', g: 250, gr: '菜' }, { n: '豆豉鲮鱼', g: 30, gr: '水产' },
        { n: '蒜', g: 5, gr: '调味' }, { n: '油', g: 8, gr: '油' }
      ],
      steps: ['鲮鱼撕小块', '爆香蒜，下油麦菜大火快炒', '放鲮鱼豆豉炒匀'],
      nutrition: { kcal: 160, protein: 8, fat: 10, carb: 10, fiber: 2, sodium: 700, vegGram: 250 },
      tip: '罐头鲮鱼偏咸，放一半带豆豉即可，别再额外加盐。' },

    { id: 'yaozhuzd', name: '瑶柱蒸蛋', kind: '清蒸', group: '素菜', style: '广府', difficulty: 1, time: 15,
      tags: ['高蛋白', '老人适宜'], veto: ['seafood'], veg: false, occa: false,
      ingredients: [
        { n: '鸡蛋', g: 100, gr: '蛋' }, { n: '干贝', g: 10, gr: '干' },
        { n: '温水', g: 250, gr: '水' }, { n: '生抽', g: 3, gr: '调味' }, { n: '油', g: 3, gr: '油' }
      ],
      steps: ['干贝温水泡发撕丝', '蛋液加水拌匀过筛，撒干贝丝', '小火蒸 12 分钟，淋几滴生抽'],
      nutrition: { kcal: 180, protein: 16, fat: 10, carb: 4, fiber: 0, sodium: 450, vegGram: 0 },
      tip: '蒸蛋嫩滑好消化，适合老人小孩；干贝自带鲜味，少盐。' },

    { id: 'suanxilan', name: '蒜蓉西兰花', kind: '素菜', group: '素菜', style: '广府', difficulty: 1, time: 10,
      tags: ['高纤维', '低卡', '减脂友好'], veto: [], veg: true, occa: false,
      ingredients: [
        { n: '西兰花', g: 250, gr: '菜' }, { n: '蒜', g: 10, gr: '调味' },
        { n: '蚝油', g: 5, gr: '调味' }, { n: '油', g: 5, gr: '油' }
      ],
      steps: ['西兰花掰小朵，盐水浸泡后焯水 1 分半', '爆香蒜末快炒或直接淋蒜蓉汁', '加蚝油拌匀'],
      nutrition: { kcal: 80, protein: 6, fat: 3, carb: 10, fiber: 4, sodium: 400, vegGram: 250 },
      tip: '西兰花热量低膳食纤维多，减脂期首选蔬菜。' },

    { id: 'qingzheng_doufu', name: '清蒸水豆腐', kind: '清蒸', group: '素菜', style: '广府', difficulty: 1, time: 15,
      tags: ['高蛋白', '含钙', '素食友好'], veto: [], veg: true, occa: false,
      ingredients: [
        { n: '水豆腐', g: 250, gr: '豆' }, { n: '虾米', g: 0, gr: '水产' },
        { n: '小葱', g: 5, gr: '调味' }, { n: '生抽', g: 5, gr: '调味' }, { n: '油', g: 3, gr: '油' }
      ],
      steps: ['水豆腐切块码盘', '大火蒸 8 分钟，倒掉蒸汁', '淋少许生抽与热油，撒葱花'],
      nutrition: { kcal: 130, protein: 12, fat: 6, carb: 5, fiber: 1, sodium: 320, vegGram: 0 },
      tip: '清淡高蛋白，素食者把它当"肉"吃就对了。' },

    // ---------- 老火汤 ----------
    { id: 'dongguayiyimi', name: '冬瓜薏米排骨汤', kind: '老火汤', group: '汤', style: '广府', difficulty: 1, time: 110,
      tags: ['清热祛湿', '夏季'], veto: [], veg: false, occa: false,
      ingredients: [
        { n: '冬瓜', g: 300, gr: '菜' }, { n: '薏米', g: 30, gr: '粮' }, { n: '排骨', g: 150, gr: '肉' },
        { n: '姜', g: 5, gr: '调味' }, { n: '盐', g: 2, gr: '调味' }
      ],
      steps: ['排骨焯水，薏米泡 30 分钟', '所有材料加水大火煮开转小火煲 90 分钟', '下冬瓜再煲 15 分钟，少量盐调味'],
      nutrition: { kcal: 260, protein: 18, fat: 16, carb: 12, fiber: 2, sodium: 520, vegGram: 300 },
      tip: '夏季祛湿好汤；排骨去油、盐放少，痛风人群少喝老火汤。' },

    { id: 'lianouhs', name: '莲藕花生猪骨汤', kind: '老火汤', group: '汤', style: '广府', difficulty: 1, time: 150,
      tags: ['滋养', '秋冬'], veto: [], veg: false, occa: false,
      ingredients: [
        { n: '莲藕', g: 250, gr: '菜' }, { n: '花生', g: 40, gr: '粮' }, { n: '猪筒骨', g: 200, gr: '肉' },
        { n: '姜', g: 5, gr: '调味' }, { n: '盐', g: 2, gr: '调味' }
      ],
      steps: ['猪骨焯水，莲藕削皮切块', '加水大火煮开转小火煲 2 小时', '调味即可'],
      nutrition: { kcal: 300, protein: 20, fat: 15, carb: 20, fiber: 5, sodium: 480, vegGram: 250 },
      tip: '莲藕是"水中人参"，秋燥季节常喝；花生油脂高，别放太多。' },

    { id: 'hongluobo', name: '红萝卜玉米猪骨汤', kind: '老火汤', group: '汤', style: '广府', difficulty: 1, time: 120,
      tags: ['清甜', '儿童爱喝'], veto: [], veg: false, occa: false,
      ingredients: [
        { n: '红萝卜', g: 150, gr: '菜' }, { n: '玉米', g: 200, gr: '粮' }, { n: '猪骨', g: 150, gr: '肉' },
        { n: '蜜枣', g: 8, gr: '干' }, { n: '姜', g: 5, gr: '调味' }, { n: '盐', g: 2, gr: '调味' }
      ],
      steps: ['猪骨焯水', '所有材料下锅，大火煮开转小火煲 90 分钟', '调味'],
      nutrition: { kcal: 240, protein: 16, fat: 12, carb: 22, fiber: 4, sodium: 460, vegGram: 150 },
      tip: '清甜可口，孩子爱喝；玉米当主食吃更好，别只喝汤。' },

    { id: 'xiyangcai', name: '西洋菜陈肾猪骨汤', kind: '老火汤', group: '汤', style: '广府', difficulty: 2, time: 120,
      tags: ['清热润肺', '换季'], veto: ['organ', 'preserved'], veg: false, occa: false,
      ingredients: [
        { n: '西洋菜', g: 200, gr: '菜' }, { n: '陈肾', g: 40, gr: '肉' }, { n: '猪骨', g: 150, gr: '肉' },
        { n: '蜜枣', g: 8, gr: '干' }, { n: '陈皮', g: 3, gr: '干' }, { n: '姜', g: 5, gr: '调味' }
      ],
      steps: ['陈肾、猪骨焯水，陈皮泡软', '加水煮开，下西洋菜小火煲 90 分钟', '调味即可'],
      nutrition: { kcal: 230, protein: 20, fat: 11, carb: 14, fiber: 4, sodium: 560, vegGram: 200 },
      tip: '西洋菜清热润肺，维生素丰富；陈肾是腊制内脏，嘌呤与盐偏高，高尿酸人群慎喝。' },

    { id: 'wuzhimaotao', name: '五指毛桃健脾鸡汤', kind: '老火汤', group: '汤', style: '广府', difficulty: 1, time: 120,
      tags: ['健脾', '换季'], veto: [], veg: false, occa: false,
      ingredients: [
        { n: '三黄鸡', g: 200, gr: '肉' }, { n: '五指毛桃', g: 20, gr: '干' },
        { n: '淮山', g: 20, gr: '干' }, { n: '红枣', g: 10, gr: '干' }, { n: '姜', g: 5, gr: '调味' }
      ],
      steps: ['鸡斩块焯水', '五指毛桃、淮山、红枣冲洗后入锅', '加水大火开转小火煲 1.5 小时，调味'],
      nutrition: { kcal: 280, protein: 24, fat: 18, carb: 10, fiber: 2, sodium: 440, vegGram: 0 },
      tip: '五指毛桃有椰子香气，健脾益气；想清淡可先剔去鸡皮再煲。' },

    // ---------- 炖汤 / 快手汤 ----------
    { id: 'fanqiedht', name: '番茄蛋花汤', kind: '炖汤', group: '汤', style: '广府', difficulty: 1, time: 12,
      tags: ['快手', '低脂', '儿童爱喝'], veto: [], veg: true, occa: false,
      ingredients: [
        { n: '番茄', g: 250, gr: '菜' }, { n: '鸡蛋', g: 50, gr: '蛋' },
        { n: '小葱', g: 3, gr: '调味' }, { n: '油', g: 5, gr: '油' }, { n: '盐', g: 2, gr: '调味' }
      ],
      steps: ['番茄炒出沙，加水煮开', '淋入蛋液成蛋花', '调味撒葱花'],
      nutrition: { kcal: 130, protein: 8, fat: 8, carb: 9, fiber: 2, sodium: 480, vegGram: 250 },
      tip: '几分钟的快手汤，少油少盐照样好喝，酸酸甜甜全家爱。' },

    { id: 'zicaixiapi', name: '紫菜虾皮蛋花汤', kind: '炖汤', group: '汤', style: '潮汕', difficulty: 1, time: 8,
      tags: ['快手', '补钙'], veto: ['seafood'], veg: false, occa: false,
      ingredients: [
        { n: '紫菜', g: 5, gr: '干' }, { n: '虾皮', g: 5, gr: '水产' }, { n: '鸡蛋', g: 50, gr: '蛋' },
        { n: '小葱', g: 3, gr: '调味' }, { n: '香麻油', g: 2, gr: '油' }
      ],
      steps: ['虾皮冲水去咸，水开放紫菜虾皮', '淋蛋液成蛋花', '出锅滴香油撒葱花'],
      nutrition: { kcal: 100, protein: 10, fat: 6, carb: 4, fiber: 1, sodium: 620, vegGram: 5 },
      tip: '虾皮补钙但含盐，先冲洗减少钠；痛风人群少放虾皮。' },

    { id: 'doufuyoutou', name: '豆腐鱼头汤', kind: '炖汤', group: '汤', style: '广府', difficulty: 2, time: 35,
      tags: ['奶白汤', '高蛋白'], veto: ['seafood'], veg: false, occa: false,
      ingredients: [
        { n: '鱼头', g: 150, gr: '水产' }, { n: '北豆腐', g: 200, gr: '豆' }, { n: '番茄', g: 100, gr: '菜' },
        { n: '姜', g: 8, gr: '调味' }, { n: '小葱', g: 3, gr: '调味' }, { n: '油', g: 5, gr: '油' }, { n: '盐', g: 2, gr: '调味' }
      ],
      steps: ['鱼头煎香，冲入热水煮至奶白', '下豆腐、番茄再煮 10 分钟', '调味撒葱花'],
      nutrition: { kcal: 220, protein: 24, fat: 10, carb: 8, fiber: 2, sodium: 560, vegGram: 100 },
      tip: '鱼头富含 DHA，豆腐补钙；煮奶白的秘诀是加热水。' },

    { id: 'dongguahaidai', name: '冬瓜海带汤', kind: '炖汤', group: '汤', style: '广府', difficulty: 1, time: 25,
      tags: ['低脂', '减脂友好'], veto: ['seafood'], veg: false, occa: false,
      ingredients: [
        { n: '冬瓜', g: 250, gr: '菜' }, { n: '海带', g: 50, gr: '干' },
        { n: '枸杞', g: 3, gr: '干' }, { n: '盐', g: 2, gr: '调味' }
      ],
      steps: ['海带泡发切片，冬瓜切块', '加水煮开转小火煮 20 分钟', '调味撒枸杞'],
      nutrition: { kcal: 70, protein: 3, fat: 1, carb: 12, fiber: 3, sodium: 420, vegGram: 250 },
      tip: '热量极低又利水，减脂期晚餐绝配；甲状腺患者遵医嘱限量吃海带。' },

    // ---------- 主食 ----------
    { id: 'fan', name: '白米饭', kind: '主食', group: '主食', style: '广府', difficulty: 1, time: 25,
      tags: ['基础美味'], veto: [], veg: true, occa: false,
      ingredients: [{ n: '大米', g: 80, gr: '粮' }],
      steps: ['米洗净浸泡 15 分钟', '加水没过一指节，电饭锅煮制'],
      nutrition: { kcal: 278, protein: 6, fat: 1, carb: 61, fiber: 1, sodium: 2, vegGram: 0 },
      tip: '搭配杂粮（糙米、燕麦）可换成杂粮饭，饱腹又控糖。' },

    { id: 'zaliangfan', name: '杂粮饭', kind: '主食', group: '主食', style: '广府', difficulty: 1, time: 35,
      tags: ['控糖', '高纤维', '全谷物'], veto: [], veg: true, occa: false,
      ingredients: [
        { n: '大米', g: 50, gr: '粮' }, { n: '糙米', g: 20, gr: '粮' },
        { n: '燕麦', g: 10, gr: '粮' }, { n: '小米或红腰豆', g: 10, gr: '粮' }
      ],
      steps: ['杂粮提前泡 40 分钟', '与大米混合加水入电饭锅', '煮好焖 10 分钟更软糯'],
      nutrition: { kcal: 280, protein: 8, fat: 2, carb: 58, fiber: 5, sodium: 2, vegGram: 0 },
      tip: '全谷物+杂豆每天都该有 50~150 克，煮饭时掺一把最简单。' },

    { id: 'zhenghongshu', name: '蒸红薯', kind: '主食', group: '主食', style: '广府', difficulty: 1, time: 25,
      tags: ['高纤维', '薯类'], veto: [], veg: true, occa: false,
      ingredients: [{ n: '红薯', g: 150, gr: '粮' }],
      steps: ['红薯洗净不去皮', '大火蒸 20~25 分钟至软'],
      nutrition: { kcal: 160, protein: 2, fat: 0, carb: 38, fiber: 4, sodium: 60, vegGram: 0 },
      tip: '薯类是优质主食，代替部分米饭；蒸着吃最健康。' },

    { id: 'laweibaozai', name: '腊味煲仔饭', kind: '煲仔', group: '主食', style: '广府', difficulty: 2, time: 45,
      tags: ['香口', '经典'], veto: ['preserved'], veg: false, occa: true,
      ingredients: [
        { n: '丝苗米', g: 100, gr: '粮' }, { n: '腊肠', g: 30, gr: '肉' }, { n: '腊肉', g: 20, gr: '肉' },
        { n: '青菜', g: 100, gr: '菜' }, { n: '豉油汁', g: 10, gr: '调味' }, { n: '油', g: 3, gr: '油' }
      ],
      steps: ['米浸 30 分钟入砂锅小火煮 8 分熟', '铺腊味，沿边淋油焗出饭焦', '下烫好的青菜，浇豉油汁'],
      nutrition: { kcal: 480, protein: 15, fat: 18, carb: 66, fiber: 2, sodium: 700, vegGram: 100 },
      tip: '腊味高盐高脂，属"偶尔吃"；饭焦虽香但含多环芳烃，少吃。' },

    { id: 'chiyouhcm', name: '豉油皇炒面', kind: '小炒', group: '主食', style: '广府', difficulty: 2, time: 15,
      tags: ['快手', '功夫面'], veto: [], veg: true, occa: false,
      ingredients: [
        { n: '生蛋面', g: 150, gr: '粮' }, { n: '韭黄', g: 30, gr: '菜' }, { n: '葱', g: 10, gr: '调味' },
        { n: '生抽', g: 10, gr: '调味' }, { n: '老抽', g: 3, gr: '调味' }, { n: '白糖', g: 3, gr: '调味' }, { n: '油', g: 8, gr: '油' }
      ],
      steps: ['生面焯水过冷沥干', '猛火快炒，加豉油糖调匀', '下韭黄葱段翻匀即可'],
      nutrition: { kcal: 380, protein: 11, fat: 10, carb: 62, fiber: 2, sodium: 900, vegGram: 30 },
      tip: '炒面用油多，减半放油更健康；当正餐记得配份白灼菜。' },

    { id: 'baizhou', name: '白粥（配小菜）', kind: '粥品', group: '主食', style: '广府', difficulty: 1, time: 40,
      tags: ['养胃', '清淡'], veto: [], veg: true, occa: false,
      ingredients: [
        { n: '大米', g: 60, gr: '粮' }, { n: '水', g: 900, gr: '水' }, { n: '扁豆或青椒小菜', g: 30, gr: '菜' }
      ],
      steps: ['米加水大火煮开', '转小火熬 30 分钟至绵滑', '配少盐小菜、水煮蛋更均衡'],
      nutrition: { kcal: 220, protein: 5, fat: 1, carb: 46, fiber: 1, sodium: 40, vegGram: 30 },
      tip: '白粥养胃但营养单薄，配蛋、豆腐、青菜才完整，别只喝白粥。' },

    { id: 'pidanzd', name: '皮蛋瘦肉粥', kind: '粥品', group: '主食', style: '广府', difficulty: 1, time: 50,
      tags: ['养胃', '经典早餐'], veto: [], veg: false, occa: false,
      ingredients: [
        { n: '大米', g: 60, gr: '粮' }, { n: '皮蛋', g: 60, gr: '蛋' }, { n: '瘦肉', g: 50, gr: '肉' },
        { n: '姜丝', g: 5, gr: '调味' }, { n: '小葱', g: 3, gr: '调味' }, { n: '盐', g: 2, gr: '调味' }
      ],
      steps: ['米加油盐泡 20 分钟，加水熬成绵粥', '下皮蛋丁、腌过的瘦肉再煮 10 分钟', '撒姜葱，少盐调味'],
      nutrition: { kcal: 330, protein: 20, fat: 12, carb: 38, fiber: 1, sodium: 680, vegGram: 0 },
      tip: '加一碟青菜或小菜，蛋白质与膳食纤维更均衡。' },

    { id: 'shengyu', name: '生滚鱼片粥', kind: '粥品', group: '主食', style: '广府', difficulty: 1, time: 45,
      tags: ['养胃', '高蛋白'], veto: ['seafood'], veg: false, occa: false,
      ingredients: [
        { n: '大米', g: 60, gr: '粮' }, { n: '草鱼片', g: 80, gr: '水产' },
        { n: '姜丝', g: 5, gr: '调味' }, { n: '生粉', g: 5, gr: '调味' }, { n: '油', g: 3, gr: '油' }, { n: '盐', g: 2, gr: '调味' }
      ],
      steps: ['熬好绵滑白粥', '鱼片用油盐生粉腌', '下锅滚一滚即关火，撒姜葱'],
      nutrition: { kcal: 300, protein: 20, fat: 5, carb: 44, fiber: 1, sodium: 520, vegGram: 0 },
      tip: '鱼片滚熟即起，营养流失最少；痛风急性期少喝。' },

    { id: 'tingzaizhou', name: '艇仔粥', kind: '粥品', group: '主食', style: '广府', difficulty: 2, time: 50,
      tags: ['经典', '料足'], veto: ['seafood'], veg: false, occa: false,
      ingredients: [
        { n: '大米', g: 60, gr: '粮' }, { n: '草鱼片', g: 40, gr: '水产' }, { n: '叉烧', g: 20, gr: '肉' },
        { n: '花生', g: 5, gr: '粮' }, { n: '鸡蛋丝', g: 25, gr: '蛋' }, { n: '油条', g: 15, gr: '粮' }
      ],
      steps: ['熬绵白粥作粥底', '碗中放鱼片、叉烧、蛋丝', '冲入滚粥，加花生油条'],
      nutrition: { kcal: 350, protein: 18, fat: 10, carb: 48, fiber: 1, sodium: 650, vegGram: 0 },
      tip: '料足味鲜，油条花生是"点睛"也增脂，减量更健康。' },

    // ---------- 点心 ----------
    { id: 'xianxiajiao', name: '鲜虾饺', kind: '点心', group: '点心', style: '广府', difficulty: 3, time: 60,
      tags: ['茶楼经典'], veto: ['seafood'], veg: false, occa: false,
      ingredients: [
        { n: '鲜虾仁', g: 80, gr: '水产' }, { n: '猪肉末', g: 20, gr: '肉' },
        { n: '澄粉', g: 50, gr: '粮' }, { n: '生粉', g: 20, gr: '粮' }, { n: '马蹄', g: 20, gr: '菜' }
      ],
      steps: ['虾肉剁成胶，加肉末马蹄调味', '澄面生粉烫成团，擀皮', '包成弯月饺，大火蒸 6 分钟'],
      nutrition: { kcal: 180, protein: 14, fat: 4, carb: 24, fiber: 1, sodium: 480, vegGram: 20 },
      tip: '虾饺是好蛋白，但早餐别只吃一笼，配粥或牛奶更完整。' },

    { id: 'zhai_changfen', name: '斋肠粉', kind: '点心', group: '点心', style: '广府', difficulty: 2, time: 20,
      tags: ['快手'], veto: [], veg: true, occa: false,
      ingredients: [
        { n: '粘米粉', g: 60, gr: '粮' }, { n: '澄面', g: 15, gr: '粮' },
        { n: '生粉', g: 15, gr: '粮' }, { n: '豉油汁', g: 10, gr: '调味' }
      ],
      steps: ['粉浆调匀静置 15 分钟', '薄浆上盘大火蒸 1 分钟', '卷起淋少许豉油汁'],
      nutrition: { kcal: 210, protein: 5, fat: 1, carb: 46, fiber: 1, sodium: 400, vegGram: 0 },
      tip: '纯碳水，吃斋肠粉记得配鸡蛋、豆浆补蛋白，豉油少淋。' },

    { id: 'rou_changfen', name: '肉片肠粉', kind: '点心', group: '点心', style: '广府', difficulty: 2, time: 25,
      tags: ['经典早餐'], veto: [], veg: false, occa: false,
      ingredients: [
        { n: '粘米粉', g: 60, gr: '粮' }, { n: '澄面', g: 15, gr: '粮' }, { n: '瘦肉片', g: 40, gr: '肉' },
        { n: '青菜', g: 50, gr: '菜' }, { n: '豉油汁', g: 10, gr: '调味' }
      ],
      steps: ['粉浆调匀，肉片用油盐腌', '倒薄浆蒸 1 分钟放肉片菜再蒸', '卷起淋豉油汁'],
      nutrition: { kcal: 240, protein: 12, fat: 4, carb: 38, fiber: 1, sodium: 560, vegGram: 50 },
      tip: '有肉有菜有碳水，是更饱满的早餐选择。' },

    { id: 'nuomiji', name: '糯米鸡', kind: '点心', group: '点心', style: '广府', difficulty: 3, time: 90,
      tags: ['宴客'], veto: [], veg: false, occa: false,
      ingredients: [
        { n: '糯米', g: 80, gr: '粮' }, { n: '鸡腿肉', g: 40, gr: '肉' }, { n: '香菇', g: 15, gr: '干' },
        { n: '叉烧', g: 15, gr: '肉' }, { n: '干荷叶', g: 1, gr: '干' }
      ],
      steps: ['糯米泡 3 小时蒸熟，鸡腿香菇叉烧炒香', '荷叶包糯米与馅料', '大火蒸 25 分钟'],
      nutrition: { kcal: 350, protein: 16, fat: 8, carb: 56, fiber: 2, sodium: 700, vegGram: 0 },
      tip: '糯米难消化，一次别多吃，老人小孩浅尝即止。' },

    { id: 'magao', name: '马拉糕', kind: '点心', group: '点心', style: '广府', difficulty: 2, time: 60,
      tags: ['茶楼经典'], veto: [], veg: true, occa: true,
      ingredients: [
        { n: '低筋面粉', g: 50, gr: '粮' }, { n: '鸡蛋', g: 50, gr: '蛋' },
        { n: '红糖', g: 20, gr: '调味' }, { n: '牛奶', g: 40, gr: '奶' }, { n: '泡打粉', g: 2, gr: '调味' }
      ],
      steps: ['面糊拌至无颗粒，静置发酵', '倒入模具', '大火蒸 20 分钟切块'],
      nutrition: { kcal: 240, protein: 7, fat: 6, carb: 41, fiber: 1, sodium: 200, vegGram: 0 },
      tip: '红糖仍是"糖"，偶尔当茶点吃；控糖人群少食。' }
  ];

  var byId = {};
  R.forEach(function (r) { byId[r.id] = r; });
  return { list: R, byId: byId };
});