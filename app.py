import sqlite3
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

# ==== streamlit 版本兼容层 ====
def _st_dataframe(df, **kw):
    """兼容新旧 streamlit：新版用 width='stretch'，旧版用 use_container_width=True"""
    if kw.get('width') == 'stretch':
        kw.pop('width')
        try:
            return st.dataframe(df, width='stretch', **kw)
        except TypeError:
            return st.dataframe(df, use_container_width=True, **kw)
    return st.dataframe(df, **kw)

import os

# ========= 基础配置 =========
DB_PATH = "lab_data.db"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "123456"

VIEW_USERNAME = "viewer"
VIEW_PASSWORD = "123456"

# ========= 质量指标看板标准定义 =========
# 来源：金昌实验路线图.docx 中的"质量指标看板"
# 格式: (数据库字段名, 显示名称, 单位, 标准下限, 标准上限, 比较类型)
# 比较类型: "gte"(>=), "lte"(<=), "eq"(=)
STANDARD_INDICATORS = [
    ("d50", "粒径(D50)", "", None, 50, "lte"),
    ("li_content", "Li", "%", 17.8, None, "gte"),
    ("p_content", "P", "%", 26.5, None, "gte"),
    ("purity_content", "含量", "%", 99.0, None, "gte"),
    ("moisture", "水分", "%", None, 0.4, "lte"),
    ("so4_content", "SO4", "%", None, 0.15, "lte"),
    ("cl_content", "Cl", "ppm", None, 100, "lte"),
    ("na_content", "Na", "ppm", None, 250, "lte"),
    ("k_content", "K", "ppm", None, 50, "lte"),
    ("ca_content", "Ca", "ppm", None, 100, "lte"),
    ("mn_content", "Mn", "ppm", None, 10, "lte"),
    ("ni_content", "Ni", "ppm", None, 20, "lte"),
    ("cu_content", "Cu", "ppm", None, 10, "lte"),
    ("pb_content", "Pb", "ppm", None, 10, "lte"),
    ("zn_content", "Zn", "ppm", None, 10, "lte"),
    ("cr_content", "Cr", "ppm", None, 20, "lte"),
    ("mg_content", "Mg", "ppm", None, 100, "lte"),
    ("fe_content", "Fe", "ppm", None, 50, "lte"),
    ("al_content", "Al", "ppm", None, 20, "lte"),
    ("b_content", "B", "ppm", None, 100, "lte"),
    ("magnetic_content", "磁性物", "ppm", None, 1, "lte"),
    ("magnetic_particles", "磁性金属颗粒", "Pcs/kg", None, 200, "lte"),
    ("cu_zn_particles", "Cu/Zn颗粒", "Pcs/kg", 0, 0, "eq"),
]

# ========= 数据库初始化 =========
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 创建samples表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS samples (
            sample_id TEXT PRIMARY KEY,
            product_type TEXT,
            process_route TEXT,
            batch_number TEXT,
            test_date TEXT,
            tester TEXT,
            remark TEXT
        )
    """)

    # 创建test_results表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_id TEXT,

            -- 检测指标 - 基础
            li_content REAL,
            p_content REAL,
            na_content REAL,
            ca_content REAL,
            mg_content REAL,
            b_content REAL,
            si_content REAL,
            cl_content REAL,
            al_content REAL,
            fe_content REAL,
            co3_content REAL,
            so4_content REAL,
            moisture REAL,

            -- 检测指标 - 看板新增
            k_content REAL,
            mn_content REAL,
            ni_content REAL,
            cu_content REAL,
            pb_content REAL,
            zn_content REAL,
            cr_content REAL,
            magnetic_content REAL,
            magnetic_particles REAL,
            cu_zn_particles REAL,
            d50 REAL,
            purity_content REAL,

            -- 收率计算相关
            raw_li_mass REAL,
            raw_p_mass REAL,
            added_li_mass REAL,
            added_p_mass REAL,
            product_mass REAL,

            li_recovery REAL,
            p_recovery REAL,

            standard_grade TEXT,

            FOREIGN KEY(sample_id) REFERENCES samples(sample_id)
        )
    """)

    # 为已有数据库动态添加新列
    all_possible_columns = [
        "k_content", "mn_content", "ni_content", "cu_content", "pb_content",
        "zn_content", "cr_content", "magnetic_content", "magnetic_particles",
        "cu_zn_particles", "d50", "purity_content"
    ]

    cursor.execute("PRAGMA table_info(test_results)")
    existing_cols = [row[1] for row in cursor.fetchall()]

    for col in all_possible_columns:
        if col not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE test_results ADD COLUMN {col} REAL")
            except Exception:
                pass

    # samples表加remark列
    cursor.execute("PRAGMA table_info(samples)")
    sample_cols = [row[1] for row in cursor.fetchall()]
    if "remark" not in sample_cols:
        try:
            cursor.execute("ALTER TABLE samples ADD COLUMN remark TEXT")
        except Exception:
            pass

    conn.commit()
    conn.close()

# ========= 收率计算 =========
def calculate_recovery(li_content, p_content, product_mass,
                       raw_li_mass, raw_p_mass,
                       added_li_mass, added_p_mass):
    li_recovery = None
    p_recovery = None

    if (
        li_content is not None
        and product_mass is not None
        and (raw_li_mass or added_li_mass)
    ):
        li_in_product = product_mass * li_content / 100.0
        total_li_input = (raw_li_mass or 0.0) + (added_li_mass or 0.0)
        if total_li_input > 0:
            li_recovery = round(li_in_product / total_li_input * 100, 2)

    if (
        p_content is not None
        and product_mass is not None
        and (raw_p_mass or added_p_mass)
    ):
        p_in_product = product_mass * p_content / 100.0
        total_p_input = (raw_p_mass or 0.0) + (added_p_mass or 0.0)
        if total_p_input > 0:
            p_recovery = round(p_in_product / total_p_input * 100, 2)

    return li_recovery, p_recovery

# ========= 数据录入 =========
def add_sample_and_result(data):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT OR REPLACE INTO samples
            (sample_id, product_type, process_route, batch_number, test_date, tester, remark)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            data["sample_id"],
            data["product_type"],
            data["process_route"],
            data["batch_number"],
            data["test_date"],
            data["tester"],
            data["remark"],
        ))

        li_recovery, p_recovery = calculate_recovery(
            data["li_content"],
            data["p_content"],
            data["product_mass"],
            data["raw_li_mass"],
            data["raw_p_mass"],
            data["added_li_mass"],
            data["added_p_mass"],
        )

        cursor.execute("""
            INSERT INTO test_results
            (sample_id,
             li_content, p_content, na_content, ca_content, mg_content,
             b_content, si_content, cl_content, al_content, fe_content,
             co3_content, so4_content, moisture,
             k_content, mn_content, ni_content, cu_content, pb_content,
             zn_content, cr_content, magnetic_content, magnetic_particles,
             cu_zn_particles, d50, purity_content,
             raw_li_mass, raw_p_mass, added_li_mass, added_p_mass, product_mass,
             li_recovery, p_recovery, standard_grade)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["sample_id"],
            data["li_content"],
            data["p_content"],
            data["na_content"],
            data["ca_content"],
            data["mg_content"],
            data["b_content"],
            data["si_content"],
            data["cl_content"],
            data["al_content"],
            data["fe_content"],
            data["co3_content"],
            data["so4_content"],
            data["moisture"],
            data.get("k_content"),
            data.get("mn_content"),
            data.get("ni_content"),
            data.get("cu_content"),
            data.get("pb_content"),
            data.get("zn_content"),
            data.get("cr_content"),
            data.get("magnetic_content"),
            data.get("magnetic_particles"),
            data.get("cu_zn_particles"),
            data.get("d50"),
            data.get("purity_content"),
            data["raw_li_mass"],
            data["raw_p_mass"],
            data["added_li_mass"],
            data["added_p_mass"],
            data["product_mass"],
            li_recovery,
            p_recovery,
            data["standard_grade"],
        ))

        conn.commit()

        msg = "数据保存成功"
        if li_recovery is not None:
            msg += f"；锂收率：{li_recovery}%"
        if p_recovery is not None:
            msg += f"；磷收率：{p_recovery}%"

        st.success(msg)

    except Exception as e:
        conn.rollback()
        st.error(f"保存失败：{e}")

    finally:
        conn.close()

# ========= 查询函数 =========
def query_by_sample_id(sample_id):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT s.sample_id,
               s.product_type,
               s.process_route,
               s.batch_number,
               s.test_date,
               s.tester,
               s.remark,
               r.li_content,
               r.p_content,
               r.na_content,
               r.ca_content,
               r.mg_content,
               r.b_content,
               r.si_content,
               r.cl_content,
               r.al_content,
               r.fe_content,
               r.co3_content,
               r.so4_content,
               r.moisture,
               r.k_content,
               r.mn_content,
               r.ni_content,
               r.cu_content,
               r.pb_content,
               r.zn_content,
               r.cr_content,
               r.magnetic_content,
               r.magnetic_particles,
               r.cu_zn_particles,
               r.d50,
               r.purity_content,
               r.raw_li_mass,
               r.raw_p_mass,
               r.added_li_mass,
               r.added_p_mass,
               r.product_mass,
               r.li_recovery,
               r.p_recovery,
               r.standard_grade
        FROM samples s
        LEFT JOIN test_results r ON s.sample_id = r.sample_id
        WHERE s.sample_id = ?
    """, conn, params=(sample_id,))
    conn.close()
    return df

def query_all_results():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT s.sample_id,
               s.product_type,
               s.process_route,
               s.batch_number,
               s.test_date,
               s.tester,
               s.remark,
               r.li_content,
               r.p_content,
               r.na_content,
               r.ca_content,
               r.mg_content,
               r.b_content,
               r.si_content,
               r.cl_content,
               r.al_content,
               r.fe_content,
               r.co3_content,
               r.so4_content,
               r.moisture,
               r.k_content,
               r.mn_content,
               r.ni_content,
               r.cu_content,
               r.pb_content,
               r.zn_content,
               r.cr_content,
               r.magnetic_content,
               r.magnetic_particles,
               r.cu_zn_particles,
               r.d50,
               r.purity_content,
               r.li_recovery,
               r.p_recovery,
               r.standard_grade
        FROM samples s
        LEFT JOIN test_results r ON s.sample_id = r.sample_id
        ORDER BY s.test_date DESC
    """, conn)
    conn.close()
    return df

def search_by_remark(keyword):
    """按备注关键词模糊搜索"""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT s.sample_id,
               s.product_type,
               s.batch_number,
               s.test_date,
               s.tester,
               s.remark,
               r.li_recovery,
               r.p_recovery,
               r.standard_grade
        FROM samples s
        LEFT JOIN test_results r ON s.sample_id = r.sample_id
        WHERE s.remark LIKE ?
        ORDER BY s.test_date DESC
    """, conn, params=(f"%{keyword}%",))
    conn.close()
    return df

# ========= 指标对比（使用看板标准） =========
def compare_with_standard(df):
    if df.empty:
        st.warning("没有查询到数据")
        return

    row = df.iloc[0]
    st.subheader("质量指标看板 - 对比结果")

    compare_data = []

    for key, name, unit, low, high, cmp_type in STANDARD_INDICATORS:
        value = row.get(key)

        if pd.isna(value):
            status = "未检测"
        elif cmp_type == "gte":
            if value >= low:
                status = "达标"
            else:
                status = f"不达标(低于{low})"
            standard_range = f">={low}{unit}"
        elif cmp_type == "lte":
            if value <= high:
                status = "达标"
            else:
                status = f"不达标(高于{high})"
            standard_range = f"<={high}{unit}"
        elif cmp_type == "eq":
            if value == high:
                status = "达标"
            else:
                status = f"不达标(应为{high})"
            standard_range = f"={high}{unit}"
        else:
            status = "未知类型"
            standard_range = "未知"

        compare_data.append({
            "指标": name,
            "实测值": f"{value}{unit}" if not pd.isna(value) else "无",
            "标准范围": standard_range,
            "结果": status,
        })

    _st_dataframe(pd.DataFrame(compare_data), width="stretch")

# ========= 样品间对比 =========
def compare_samples(sample_ids, element):
    if not sample_ids:
        st.warning("请至少输入一个样品编号")
        return

    conn = sqlite3.connect(DB_PATH)
    placeholders = ",".join(["?"] * len(sample_ids))
    df = pd.read_sql_query(
        f"SELECT sample_id, {element} FROM test_results WHERE sample_id IN ({placeholders})",
        conn,
        params=sample_ids,
    )
    conn.close()

    if df.empty:
        st.warning("未找到对比数据")
        return

    _st_dataframe(df, width="stretch")

    fig, ax = plt.subplots()
    ax.bar(df["sample_id"].astype(str), df[element])
    ax.set_title(f"{element} 样品对比")
    ax.set_xlabel("样品编号")
    ax.set_ylabel(element)
    plt.xticks(rotation=45)
    st.pyplot(fig)

# ========= 登录状态 =========
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.role = None

if "selected_sample_id" not in st.session_state:
    st.session_state.selected_sample_id = None

def login_page():
    st.title("实验数据系统登录")

    username = st.text_input("用户名")
    password = st.text_input("密码", type="password")

    if st.button("登录"):
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            st.session_state.logged_in = True
            st.session_state.role = "admin"
            st.success("管理员登录成功")
            st.rerun()
        elif username == VIEW_USERNAME and password == VIEW_PASSWORD:
            st.session_state.logged_in = True
            st.session_state.role = "viewer"
            st.success("查看模式登录成功")
            st.rerun()
        else:
            st.error("用户名或密码错误")

def logout():
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.selected_sample_id = None
    st.rerun()

# ========= 主程序 =========
init_db()

if not st.session_state.logged_in:
    login_page()
    st.stop()

st.sidebar.title("导航")
st.sidebar.write(f"当前身份：{st.session_state.role}")

if st.sidebar.button("退出登录"):
    logout()

menu = ["数据查询", "指标对比", "样品对比"]

if st.session_state.role == "admin":
    menu.insert(0, "数据录入")

choice = st.sidebar.selectbox("选择功能", menu)

# ========= 数据录入 =========
if choice == "数据录入" and st.session_state.role == "admin":
    st.title("录入检测结果")

    with st.form("add_form"):
        sample_id = st.text_input("样品编号")
        product_type = st.selectbox(
            "产品类型",
            ["电池级磷酸锂", "电池级磷酸二氢锂", "其他"],
        )
        process_route = st.text_input("工艺路线")
        batch_number = st.text_input("批次号")
        test_date = st.date_input("检测日期")
        tester = st.text_input("检测人员")
        remark = st.text_area("备注")

        st.subheader("检测指标 - 基础项")

        li_content = st.number_input("锂含量 Li %", step=0.01)
        p_content = st.number_input("磷含量 P %", step=0.01)
        na_content = st.number_input("钠含量 Na", step=0.01)
        ca_content = st.number_input("钙含量 Ca", step=0.01)
        mg_content = st.number_input("镁含量 Mg", step=0.01)
        b_content = st.number_input("硼含量 B", step=0.01)
        si_content = st.number_input("硅含量 Si", step=0.01)
        cl_content = st.number_input("氯离子 Cl", step=0.01)
        al_content = st.number_input("铝含量 Al", step=0.01)
        fe_content = st.number_input("铁含量 Fe", step=0.01)
        co3_content = st.number_input("碳酸根 CO3", step=0.01)
        so4_content = st.number_input("硫酸根 SO4", step=0.01)
        moisture = st.number_input("含水量/水分 %", step=0.01)

        st.subheader("检测指标 - 质量看板新增项")

        k_content = st.number_input("钾含量 K", step=0.01)
        mn_content = st.number_input("锰含量 Mn", step=0.01)
        ni_content = st.number_input("镍含量 Ni", step=0.01)
        cu_content = st.number_input("铜含量 Cu", step=0.01)
        pb_content = st.number_input("铅含量 Pb", step=0.01)
        zn_content = st.number_input("锌含量 Zn", step=0.01)
        cr_content = st.number_input("铬含量 Cr", step=0.01)
        magnetic_content = st.number_input("磁性物", step=0.01)
        magnetic_particles = st.number_input("磁性金属颗粒", step=0.01)
        cu_zn_particles = st.number_input("Cu/Zn颗粒", step=0.01)
        d50 = st.number_input("粒径(D50)", step=0.01)
        purity_content = st.number_input("含量/纯度 %", step=0.01)

        st.subheader("收率计算相关数据")

        raw_li_mass = st.number_input("原料锂质量 g", step=0.01)
        raw_p_mass = st.number_input("原料磷质量 g", step=0.01)
        added_li_mass = st.number_input("添加锂质量 g", step=0.01)
        added_p_mass = st.number_input("添加磷质量 g", step=0.01)
        product_mass = st.number_input("产物质量 g", step=0.01)

        standard_grade = st.selectbox(
            "是否达标",
            ["未判定", "达标", "不达标"],
        )

        submitted = st.form_submit_button("保存数据")

        if submitted:
            if not sample_id:
                st.error("样品编号不能为空")
            else:
                add_sample_and_result({
                    "sample_id": sample_id,
                    "product_type": product_type,
                    "process_route": process_route,
                    "batch_number": batch_number,
                    "test_date": str(test_date),
                    "tester": tester,
                    "remark": remark,
                    "li_content": li_content,
                    "p_content": p_content,
                    "na_content": na_content,
                    "ca_content": ca_content,
                    "mg_content": mg_content,
                    "b_content": b_content,
                    "si_content": si_content,
                    "cl_content": cl_content,
                    "al_content": al_content,
                    "fe_content": fe_content,
                    "co3_content": co3_content,
                    "so4_content": so4_content,
                    "moisture": moisture,
                    "k_content": k_content,
                    "mn_content": mn_content,
                    "ni_content": ni_content,
                    "cu_content": cu_content,
                    "pb_content": pb_content,
                    "zn_content": zn_content,
                    "cr_content": cr_content,
                    "magnetic_content": magnetic_content,
                    "magnetic_particles": magnetic_particles,
                    "cu_zn_particles": cu_zn_particles,
                    "d50": d50,
                    "purity_content": purity_content,
                    "raw_li_mass": raw_li_mass,
                    "raw_p_mass": raw_p_mass,
                    "added_li_mass": added_li_mass,
                    "added_p_mass": added_p_mass,
                    "product_mass": product_mass,
                    "standard_grade": standard_grade,
                })

# ========= 数据查询 =========
elif choice == "数据查询":
    st.title("数据查询")

    # --- 按样品编号查询 ---
    st.subheader("按样品编号查询")
    sample_id = st.text_input("输入样品编号", key="query_sample_id")

    if st.button("查询样品", key="btn_query_sample"):
        if not sample_id:
            st.warning("请输入样品编号")
        else:
            df = query_by_sample_id(sample_id)
            if df.empty:
                st.warning("未找到该样品数据")
            else:
                _st_dataframe(df, width="stretch")

    # --- 按备注关键词搜索 ---
    st.subheader("按备注关键词搜索")
    remark_keyword = st.text_input("输入备注中的关键词", key="search_remark")

    if st.button("搜索备注", key="btn_search_remark"):
        if not remark_keyword:
            st.warning("请输入关键词")
        else:
            results = search_by_remark(remark_keyword)
            if results.empty:
                st.warning(f"未找到备注中包含「{remark_keyword}」的样品")
            else:
                st.success(f"找到 {len(results)} 条结果")
                _st_dataframe(results, width="stretch")

                st.markdown("#### 点击查看详情")
                for idx, row in results.iterrows():
                    sid = row["sample_id"]
                    remark_text = row["remark"] if pd.notna(row["remark"]) else "无备注"
                    test_dt = row["test_date"]
                    li_rec = f"{row['li_recovery']}%" if pd.notna(row.get("li_recovery")) else "未计算"
                    p_rec = f"{row['p_recovery']}%" if pd.notna(row.get("p_recovery")) else "未计算"

                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"**{sid}** | {test_dt} | 备注：{remark_text} | 锂收率：{li_rec} | 磷收率：{p_rec}")
                    with col2:
                        if st.button("查看详情", key=f"detail_{sid}"):
                            st.session_state.selected_sample_id = sid
                            st.rerun()

    # --- 查看选中样品的完整数据 ---
    if st.session_state.selected_sample_id:
        st.subheader(f"样品详情：{st.session_state.selected_sample_id}")
        detail_df = query_by_sample_id(st.session_state.selected_sample_id)
        if not detail_df.empty:
            _st_dataframe(detail_df, width="stretch")
        if st.button("关闭详情", key="close_detail"):
            st.session_state.selected_sample_id = None
            st.rerun()

    # --- 全部数据 ---
    st.subheader("全部数据")
    _st_dataframe(query_all_results(), width="stretch")

# ========= 指标对比 =========
elif choice == "指标对比":
    st.title("与指标对比（质量指标看板）")

    sample_id = st.text_input("样品编号")

    st.info("以下标准范围来源于「金昌实验路线图」中的质量指标看板，可直接对照使用。")

    if st.button("开始对比", key="btn_compare"):
        if not sample_id:
            st.warning("请输入样品编号")
        else:
            df = query_by_sample_id(sample_id)
            compare_with_standard(df)

# ========= 样品对比 =========
elif choice == "样品对比":
    st.title("样品间对比")

    sample_ids_text = st.text_input(
        "输入多个样品编号，用逗号分隔",
        placeholder="例如：S20261020-01,S20261020-02,S20261020-03",
    )

    element = st.selectbox(
        "选择对比指标",
        [
            "li_content",
            "p_content",
            "na_content",
            "ca_content",
            "mg_content",
            "b_content",
            "si_content",
            "cl_content",
            "al_content",
            "fe_content",
            "co3_content",
            "so4_content",
            "moisture",
            "k_content",
            "mn_content",
            "ni_content",
            "cu_content",
            "pb_content",
            "zn_content",
            "cr_content",
            "magnetic_content",
            "magnetic_particles",
            "cu_zn_particles",
            "d50",
            "purity_content",
            "li_recovery",
            "p_recovery",
        ],
    )

    if st.button("对比样品"):
        if not sample_ids_text:
            st.warning("请输入样品编号")
        else:
            ids = [x.strip() for x in sample_ids_text.split(",") if x.strip()]
            if not ids:
                st.warning("请输入有效的样品编号")
            else:
                compare_samples(ids, element)
