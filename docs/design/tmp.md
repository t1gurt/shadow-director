助成金申請における自律型取得エージェントのシステムアーキテクチャ：Google Search GroundingとPlaywright MCPの統合による高確率な情報取得の実現エグゼクティブサマリー本レポートは、日本国内の官公庁（特に経済産業省および厚生労働省）が管轄する助成金・補助金制度において、その募集要項（ガイドライン）および申請フォーマット（様式）を、自律型AIエージェントを用いて高確率かつ高精度に取得するためのシステムアーキテクチャと処理フローを設計・提案するものである。従来のWebスクレイピング技術は、頻繁なURL変更、動的なDOM構造、そしてPDFやExcelといった非構造化データの混在により、長期間の安定運用が極めて困難であった。これに対し、本設計ではGoogle Search Groundingによる「動的な情報探索能力（Discovery）」と、Playwright MCP（Model Context Protocol）による「セキュアで柔軟なブラウザ操作能力（Action）」を統合したSGNA（Search-Ground-Navigate-Act）モデルを採用する。このアーキテクチャは、単なる情報の収集にとどまらず、取得したファイルが「最新の公募回（例：第19回）」に対応するものであるかを検証する自己回帰的なプロセスを包含しており、行政DX（デジタルトランスフォーメーション）における高度な自動化基盤としての利用を想定している。1. 序論：行政情報の非構造性と自律型エージェントの必要性1.1 背景：助成金情報の流動性と取得の課題日本の中小企業支援策において、ものづくり補助金やキャリアアップ助成金などの制度は経営資源として極めて重要である。しかし、これらの情報は各省庁のWebサイト、特設サイト、事務局サイトに分散しており、さらに以下の特徴を持つため、機械的な取得を困難にしている。情報の時間的局所性: 助成金は「公募回（ラウンド）」ごとに管理される。過去の回の要項と最新の要項が同一ドメイン内に混在しており、単純なキーワード検索では「第18回（終了分）」のファイルを誤取得するリスクが高い。ファイル形式の多様性: 募集要項はPDFで提供される一方、申請フォーマットはWord、Excel、あるいはこれらを圧縮したZIP形式で提供される。これらを適切にハンドリングし、内容を検証する必要がある。ナビゲーションの複雑性: 厚生労働省のサイトのように、単一ページ内に数十種類の助成金リンクが羅列される「リスト型」構造や、ものづくり補助金事務局サイトのようなJavaScriptを多用した「動的」構造など、サイトごとのUIパターンの差異が大きい1。1.2 従来型アプローチの限界従来の固定的なスクリプト（BeautifulSoupやSeleniumを用いたハードコードされたスクレイピング）は、DOM構造の些細な変更やURLの更新により即座に機能不全に陥る。また、LLM（大規模言語モデル）単独では、学習データのカットオフ（知識の期限切れ）により、最新の公募情報を正しく認識できない「幻覚（ハルシネーション）」の問題が発生する。1.3 提案手法：SGNAモデルの採用本レポートで設計するシステムは、これらの課題を解決するためにSGNA（Search-Ground-Navigate-Act）モデルを提唱する。これは、Google Search Groundingによって「現在の正解URL」を特定し（Grounding）、Playwright MCPによって「物理的な取得行動」を実行する（Navigate & Act）という、認知と行動を分離・連携させるアーキテクチャである。2. システムアーキテクチャ概要本システムは、オーケストレーション層、グランディング層、実行層、検証層の4つの主要コンポーネントで構成される。各層はModel Context Protocol (MCP) を介して疎結合に連携し、柔軟な拡張性と保守性を担保する。2.1 全体構成図（概念）システムの中核には、高度な推論能力を持つLLM（Gemini 2.0 Pro等）が配置され、MCPサーバー群をツールとして操作する「オーケストレーター」として機能する。レイヤーコンポーネント主要技術・ツール役割オーケストレーション層Agent CoreGemini 2.0 / Vertex AIタスク分解、意思決定、エラーハンドリング、MCPツールの呼び出しグランディング層Discovery EngineGoogle Search Grounding API最新情報の検索、公式サイトの特定、ドメインフィルタリング実行層Browser ServerPlaywright MCP Serverブラウザ操作、DOM解析、ファイルダウンロード、スクリーンショット撮影検証層ValidatorPDF Reader MCP / File Parser取得ファイルのテキスト抽出、公募回数の整合性チェック永続化層StorageLocal / Cloud Storage (S3等)取得アーティファクトの保存、ログ管理2.2 Model Context Protocol (MCP) の採用意義MCPは、AIモデルと外部ツール（ブラウザ、ファイルシステム、データベース）を接続するための標準プロトコルである3。本システムにおいてMCPを採用する利点は以下の通りである。ツールの標準化: Playwrightの複雑なAPI（page.goto, locator.click, download.saveAs）を、LLMが理解しやすいJSONスキーマとして定義・公開できる4。コンテキストの保持: ブラウザの状態（セッション、Cookie、現在のURL）をMCPサーバー側で管理し、LLMはステートレスな推論に集中できる。これにより、複数のページを遷移しながら情報を探索するマルチステップのタスクが可能となる。拡張性: 将来的にPDF解析ツールやOCRツールを追加する際、MCPサーバーとして追加するだけで、エージェントの能力を容易に拡張できる5。3. 詳細設計：Google Search Groundingによる「情報の特定」プロセスの第一段階は、目的の助成金情報の「ありか」を特定することである。ここではGoogle Search Groundingを活用し、LLMの内部知識ではなく、リアルタイムのWebインデックスに基づく探索を行う。3.1 ダイナミック・リトリーバル設定 (Dynamic Retrieval Configuration)Google Search Grounding APIには、検索を実行するか否かを動的に判断するdynamic_retrieval_configが存在する6。しかし、助成金情報は常に最新性が求められるため、本システムでは動的判断（Dynamic）ではなく、**強制的検索（Always Grounding）**に近い戦略、あるいは非常に低い閾値（dynamic_threshold = 0.3以下）を設定することを推奨する8。推奨設定:Mode: Global Search (Web全体)Site Restrictions: 信頼性を担保するため、検索クエリにsite:go.jp（政府機関）、site:or.jp（公的団体）、および特定の事務局ドメイン（例：monohojo.info）を付与するフィルタリングロジックをプロンプトレベルで実装する9。3.2 クエリ生成戦略ユーザーの抽象的な要求（例：「ものづくり補助金の最新のやつ」）を、検索エンジンに最適化されたクエリに変換する。入力: 「ものづくり補助金の申請書が欲しい」変換後クエリ: "ものづくり補助金" "公募要領" "最新" "申請様式" "ダウンロード" site:monohojo.info OR site:go.jpこのように、filetype:pdfやfiletype:xlsxなどの演算子を組み合わせることで、直接ファイルへのリンクを探すか、ダウンロードリンクを含む「着陸ページ（Landing Page）」を探すかを戦略的に切り替える。本アーキテクチャでは、着陸ページの特定を優先する。直接ファイルへのリンクはリンク切れのリスクが高く、また「最新版」かどうかの文脈判断が難しいためである。3.3 検索結果の検証検索結果として返されるメタデータ（スニペット、タイトル、URL）をLLMが解析し、以下の基準でターゲットURLを選定する。ドメインの正当性: 公式ドメインであるか。情報の鮮度: スニペットに含まれる日付や「第X回」という表記が、現在の日付と比較して妥当か。ページの種類: PDFへの直リンクではなく、HTMLページ（インデックスページ）であることを優先する。4. 詳細設計：Playwright MCPによる「情報の取得」ターゲットURLが特定された後、Playwright MCPサーバーが物理的なアクセスと操作を行う。ここはシステムの中で最も複雑性が高い部分であり、高度な例外処理が求められる。4.1 Playwright MCPサーバーの機能拡張標準的なPlaywright MCPサーバー4は、基本的なナビゲーションやクリック機能を提供するが、ファイルダウンロードのハンドリングにはカスタマイズが必要となる場合が多い。特に、ヘッドレスブラウザ環境におけるダウンロードイベントの捕捉とファイル保存は、明示的な実装が必要である11。必要なカスタムツール定義Tool名: download_resourceこのツールは、指定されたセレクタをクリックし、発生したダウンロードイベントを捕捉して、永続ストレージに保存する。JSON{
  "name": "download_resource",
  "description": "指定された要素をクリックし、ファイルのダウンロードを完了させ、保存されたパスを返す。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "selector": {
        "type": "string",
        "description": "クリックする要素のCSSセレクタまたはXPath"
      },
      "expected_extension": {
        "type": "string",
        "description": "期待されるファイル拡張子（例:.xlsx,.pdf,.zip）"
      },
      "timeout": {
        "type": "integer",
        "description": "待機時間（ミリ秒）。デフォルトは30000"
      }
    },
    "required": ["selector"]
  }
}
内部処理ロジック（TypeScriptイメージ）:TypeScript// Playwrightによるダウンロード処理の実装イメージ
const [download] = await Promise.all([
  page.waitForEvent('download'), // ダウンロードイベントの待機
  page.locator(selector).click(), // トリガーとなるクリック
]);
const suggestedName = download.suggestedFilename();
const savePath = `/data/downloads/${uuid()}_${suggestedName}`;
await download.saveAs(savePath); // 一時フォルダから永続化
return { status: "success", path: savePath, filename: suggestedName };
この実装により、LLMは「クリック」という抽象的な指示ではなく、「ファイルをダウンロードして保存せよ」という明確なインテントを持ってブラウザを操作できる11。4.2 DOM解析とアクセシビリティツリーの活用政府系サイトはDOM構造が深く、class名が難読化されていたり、意味を持たないdivのネストが多用されていたりする。Playwright MCPは、生のHTMLではなく**アクセシビリティツリー（Accessibility Tree）**のスナップショットをLLMに提供することで、この問題を回避する4。利点: 視覚的・意味的な構造（「リンク」「ボタン」「見出し」）のみが抽出されるため、HTMLの変更に対して堅牢である。戦略: LLMは「class="btn-dl"を探す」のではなく、「"公募要領"というラベルを持つリンクを探す」というセマンティックな探索を行う。5. ケーススタディ別処理フロー具体的なサイト構造に基づき、エージェントがどのように振る舞うべきかを設計する。5.1 ケーススタディA：ものづくり補助金（動的・モダンなサイト）サイト特性:事務局サイト（monohojo.info）2は比較的モダンな作りだが、JavaScriptによる動的なコンテンツ描画が多い。「公募要領」ページには、過去の回のデータがアーカイブとして残されている場合がある。申請は電子申請システムへのリンクが主だが、要項（PDF）と書式（Word/Excel）はダウンロードリンクとして提供される。処理フロー:Grounding: site:monohojo.info "公募要領" "最新" で検索。最新の公募回（例：第19回）のページURLを取得。Navigation: PlaywrightでURLを開く。networkidleステートを待機し、動的コンテンツの読み込み完了を保証する。Semantic Parsing: ページ内の見出し（Heading）レベル1〜3をスキャンし、「第19回」または最新の日付を含むセクションを特定する。Targeting: 特定したセクション内にある、「公募要領（PDF）」および「様式（ZIP/Word）」というテキストを含むリンクを特定。Action: download_resourceツールを実行。注意点: ZIPファイルの場合、解凍ツール（後述）による展開が必要となる。5.2 ケーススタディB：厚生労働省 キャリアアップ助成金（静的・リスト型・複雑）サイト特性:厚生労働省のページ1は、極めて長いページに多数のコース（正社員化コース、賃金規定等改定コースなど）の情報が羅列されている。「共通様式（Form 3）」と「コース別添付様式（Attachment）」が分かれている。ファイルリンクは「Excel」や「PDF」のアイコン画像であることが多く、テキストリンクではない場合がある。また、リンクテキストが「様式第3号」のように抽象的である。処理フロー:Grounding: site:mhlw.go.jp "キャリアアップ助成金" "申請様式" "令和6年度" で検索。年度（Reiwa 6/2024など）を指定することが必須。Navigation: ページを開く。Hierarchical Context: LLMはアクセシビリティツリーから階層構造を理解する必要がある。H2: 「キャリアアップ助成金」H3: 「申請様式のダウンロード（令和6年度）」H4: 「正社員化コース」List Item: 「様式第3号（別添様式1-1）... Excel」Distinction: 1の情報に基づき、LLMは以下の判断を行う。「支給申請書（様式第3号）」は全コース共通で必要。「内訳（別添様式）」はコースごとに異なる。PDF版ではなく、入力可能なExcel/Word版を選択する（拡張子によるフィルタリング）。Action: 必要な複数のファイルを順次ダウンロードする。6. 「高確率」を実現するための検証ループとエラー回復単にダウンロードするだけでは不十分である。取得したファイルが正しいものであるかを検証するプロセスこそが、本アーキテクチャの肝である。6.1 PDF解析による内容検証 (Validation via PDF Parsing)ダウンロードしたファイル（特に募集要項PDF）の内容を検証するために、PDF Reader MCP5をシステムに組み込む。検証プロセス:Text Extraction: ダウンロードしたPDFの最初の3ページからテキストを抽出する。Assertion: LLMに対し、以下の事実確認を行わせる。「この文書のタイトルは『ものづくり補助金公募要領』か？」「記載されている公募回数は、検索時にターゲットとした『第19回』と一致するか？」「文書の日付は最新か（過去1年以内か）？」Feedback: 検証が失敗した場合（例：第18回の要項だった場合）、システムは「ページ内の別のリンクを試行する」または「検索クエリを修正して再検索する」という自己修復フェーズに移行する。6.2 ZIP/Excelファイルの構造検証申請フォーマットがZIPやExcelの場合、中身の構造を確認する。Excel: excel-reader-mcp（仮称・またはPythonスクリプトツール）を用い、シート名やA1セルの値を読み取る。「様式第3号」という文字列が含まれているかを確認する。ZIP: 解凍し、ファイルリストを取得。期待されるファイル群（「計画書.docx」「申請書.xlsx」など）が含まれているかをチェックする。6.3 エラーハンドリング戦略Web操作には予期せぬエラーが付き物である。Playwright MCPにおける主要なエラーとその対策を定義する。エラー種類具体例対策（MCPレベルでの実装）Selector Error指定したボタンが見つからないRetry with Vision: セレクタ探索に失敗した場合、スクリーンショットを撮影し、マルチモーダルLLMに視覚的にボタンの位置（座標）を特定させ、座標クリックを行う14。Timeoutページの読み込みが終わらないProgressive Wait: domcontentloaded → networkidle と待機条件を緩めながらリトライする。Auth Wallポップアップや認証画面が出るContext Injection: 予期せぬポップアップ（「アンケートにご協力ください」等）が出た場合、LLMにスクリーンショットを見せ、「閉じる」ボタンを押す判断をさせる。Dead Link404エラーBack & Search: ブラウザの「戻る」を実行し、Google Search Groundingの結果リストにある「2番目の候補」のURLへ遷移する。7. 実装に向けた技術要件とインフラ7.1 推奨技術スタックLLM: Gemini 1.5 Pro / 2.0 Pro (長いコンテキストウィンドウと高い推論能力が必要)Platform: Vertex AI Agent Builder (Grounding機能の統合が容易)Runtime: Node.js (Playwright MCP Server), Python (Validation Scripts)Browser: Chromium (Headless mode)7.2 セキュリティとコンプライアンス政府系サイトへのアクセスにあたっては、以下のマナーとセキュリティを遵守する設計とする。Rate Limiting: site:go.jpへのアクセスは、最小でも1秒以上のインターバル（Politeness Delay）を設けるようMCPサーバー側で制御する。User-Agent: 明示的なBot識別子を含め、管理者側がアクセス元を特定できるようにする。Sandbox: ダウンロードしたファイルにはマクロウイルスが含まれる可能性があるため、ファイル操作は隔離されたコンテナ内でのみ行い、ホストシステムへの影響を防ぐ。7.3 実装コード例：Google Search Grounding設定 (Python)GoogleのSearch Groundingを呼び出す際の設定例を示す。ここでは情報の鮮度を優先するための設定を行う6。Pythonfrom google.genai import types

# 助成金検索用ツール定義
retrieval_tool = types.Tool(
    google_search_retrieval=types.GoogleSearchRetrieval(
        dynamic_retrieval_config=types.DynamicRetrievalConfig(
            mode=types.DynamicRetrievalConfigMode.MODE_DYNAMIC,
            dynamic_threshold=0.3  # 閾値を低く設定し、積極的に検索させる
        )
    )
)

# 生成設定
config = types.GenerateContentConfig(
    tools=[retrieval_tool],
    response_modalities=,
    temperature=0.1 # 事実に基づく正確性を重視するため低く設定
)
8. 結論本レポートで設計したシステムアーキテクチャは、Google Search Groundingによる「正確なナビゲーション」と、Playwright MCPによる「柔軟な実行能力」を融合させることで、従来の課題であった「情報の見つけにくさ」と「取得の不安定さ」を同時に解決するものである。特に、単なる取得に留まらず、PDF解析MCPを用いた**コンテンツ検証ループ（Validation Loop）**を組み込むことで、「高確率」な取得を実現する点に新規性がある。これは、人間がWebサイトを見て「これは古い情報だから別のリンクを探そう」と判断する認知プロセスを、システム的に再現したものである。ものづくり補助金や厚生労働省の助成金といった、構造が複雑で変更頻度の高い行政情報を自動取得するエージェントの実装において、本アーキテクチャは堅牢かつ拡張性の高い基盤となることが期待される。行政サービスのDXが進む中、このような「ラストワンマイル」を埋める技術の実装は、企業の生産性向上に直結する重要な投資となるであろう。