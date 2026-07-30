# مرصد الذهب والفضة

تطبيق Streamlit عربي لمتابعة السعر الاسترشادي للذهب والفضة بالدرهم الإماراتي، مع حاسبة مصنعية وسجل مشتريات وتنبيهات محلية.

## التشغيل

```powershell
python -m pip install -r requirements.txt
Copy-Item .streamlit/secrets.toml.example .streamlit/secrets.toml
# ضع مفتاح Metals.Dev داخل secrets.toml
python -m streamlit run app.py
```

سيفتح Streamlit التطبيق تلقائيًا، أو استخدم العنوان الذي يظهر في الطرفية (عادةً `http://localhost:8501`).

## مصدر الأسعار

يستخدم التطبيق نقطة `latest` من [Metals.Dev](https://metals.dev/docs) مع `currency=AED` و`unit=g`. يلزم مفتاح API خاص بك. لا يحتوي المشروع على مفتاح أو أسعار وهمية. عند فشل الاتصال، تُعرض آخر قراءة ناجحة بوسم واضح بأنها محفوظة.

## البيانات المحلية

ينشئ التطبيق مجلد `.gold_observatory` محليًا، وفيه:

- `observatory.db`: المشتريات والتنبيهات.
- `last_prices.json`: آخر قراءة سعر ناجحة.

لا تُرسل هذه البيانات إلى أي خدمة أخرى.
