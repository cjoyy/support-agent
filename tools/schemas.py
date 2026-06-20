from __future__ import annotations


schemas = [
    {
        "name": "search_knowledge_base",
        "description": (
            "Gunakan untuk pertanyaan support umum yang kemungkinan jawabannya ada di FAQ/knowledge base, "
            "seperti refund, shipping, login, akun, billing, atau kebijakan layanan. Jangan dipakai untuk "
            "status order spesifik, pembuatan tiket, atau saat user jelas meminta manusia. Tool ini untuk "
            "menjawab pertanyaan informasi umum, bukan untuk mencatat kasus baru."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Pertanyaan pengguna yang perlu dicari di knowledge base.",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "check_order_status",
        "description": (
            "Gunakan hanya jika user menanyakan status order yang spesifik dan menyebutkan order ID. "
            "Order ID biasanya berbentuk seperti ORD123. Jangan dipakai untuk pertanyaan kebijakan, refund umum, "
            "shipping umum, atau FAQ umum karena tool ini hanya untuk lookup order."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "Order ID yang ingin dicek statusnya.",
                }
            },
            "required": ["order_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_ticket",
        "description": (
            "Gunakan ketika user meminta dibuatkan tiket, nomor tiket, pencatatan komplain, atau follow-up formal. "
            "Juga gunakan jika masalah butuh tracking oleh tim support. Jangan dipakai untuk pertanyaan FAQ umum, "
            "lookup status order sederhana, atau permintaan bicara langsung dengan manusia."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "issue": {
                    "type": "string",
                    "description": "Ringkasan masalah customer yang perlu dibuatkan ticket.",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Prioritas ticket berdasarkan urgensi issue.",
                },
            },
            "required": ["issue", "priority"],
            "additionalProperties": False,
        },
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Gunakan jika user secara eksplisit meminta manusia/human agent/agent support asli, jika user frustrasi "
            "atau komplain berulang, jika jawaban tidak yakin, atau jika hasil knowledge base/order lookup tidak "
            "cukup untuk menjawab dengan aman. Tool ini untuk handoff ke agent manusia, bukan untuk membuat tiket."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Alasan kenapa percakapan perlu diteruskan ke manusia.",
                }
            },
            "required": ["reason"],
            "additionalProperties": False,
        },
    },
]
