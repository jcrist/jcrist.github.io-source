Title: Dask and Scikit-Learn -- Putting it all together
Date: 2016-07-26 16:30
Category: dask
Tags: dask
Slug: dask-sklearn-part-3
Author: Jim Crist
Summary: Combining model-parallelism and data-parallelism

*Note: This post is old, and discusses an experimental library that no longer
exists. Please see [this post on `dask-searchcv`]({filename}/dask_searchcv.md),
and the [corresponding
documentation](http://dask-searchcv.readthedocs.io/en/latest/) for the current
state of things.*

This is part 3 of a series of posts discussing [recent
work](https://github.com/dask/dask-learn) with dask and scikit-learn.

- [In part 1]({filename}/dask_learn_part_1.md) we discussed model-parallelism
  &mdash; fitting several models across the same data. We found that in some
  cases we could eliminate repeated work, resulting in improved performance of
  `GridSearchCV` and `RandomizedSearchCV`.

- [In part 2]({filename}/dask_learn_part_2.md) we discussed patterns for
  data-parallelism &mdash; fitting a single model on partitioned data. We found
  that by implementing simple parallel patterns with a scikit-learn compatible
  interface we could fit models on larger datasets in a clean and standard way.

In this post we'll combine these concepts together to do distributed learning
and grid search on a real dataset; namely the
[airline dataset](http://stat-computing.org/dataexpo/2009/the-data.html). This
contains information on every flight in the USA between 1987 and 2008. It's
roughly 121 million rows, so it could be worked with on a single machine -
we'll use it here for illustration purposes only.

I'm running this on a 4 node cluster of `m3.2xlarge` instances (8 cores, 30 GB
RAM each), with one worker sharing a node with the scheduler.

    ::Python
    from distributed import Executor, progress
    exc = Executor('172.31.11.71:8786', set_as_default=True)
    exc
<div class=md_output>

    <Executor: scheduler="172.31.11.71:8786" processes=4 cores=32>
</div>


## Loading the data

I've put the csv files up on S3 for faster access on the aws cluster. We can
read them into a dask dataframe using `read_csv`. The `usecols` keyword
specifies the subset of columns we want to use. We also pass in `blocksize` to
tell dask to partition the data into larger partitions than the default.

    ::Python
    import dask.dataframe as dd

    # Subset of the columns to use
    cols = ['Year', 'Month', 'DayOfWeek', 'DepDelay',
            'CRSDepTime', 'UniqueCarrier', 'Origin', 'Dest']

    # Create the dataframe
    df = dd.read_csv('s3://dask-data/airline-data/*.csv',
                     usecols=cols,
                     blocksize=int(128e6),
                     storage_options=dict(anon=True))
    df
<div class=md_output>

    <dd.DataFrame<from-de..., npartitions=104>
</div>

Note that this hasn't done any work yet, we've just built up a graph specifying
where to load the dataframe from. Before we actually compute, lets do a few
more preprocessing steps:

- Create a new column `"delayed"` indicating whether a flight was delayed
  longer than 15 minutes or cancelled. This will be our target variable when
  fitting the estimator.

- Create a new column `"hour"` that is just the hour value from `"CRSDepTime"`.

- Drop both the `"DepDelay"` column (using how much a flight is delayed to
  predict if a flight is delayed would be cheating :) ), and the `"CRSDepTime"`
  column.

These all can be done using normal pandas operations:

    ::Python
    df = (df.drop(['DepDelay', 'CRSDepTime'], axis=1)
            .assign(hour=df.CRSDepTime.clip(upper=2399)//100,
                    delayed=(df.DepDelay.fillna(16) > 15).astype('i8')))


After setting up all the preprocessing, we can call `Executor.persist` to fully
compute the dataframe and cache it in memory across the cluster. We do this
because it can easily fit in distributed memory, and will speed up all of the
remaining steps (I/O can be expensive).

    ::Python
    exc.persist(df)

    progress(df, notebook=False)
<div class=md_output>

    [########################################] | 100% Completed |  1min 17.7s
</div>


    ::Python
    df
<div class=md_output>

    dd.DataFrame<_assign..., npartitions=104>
</div>


    ::Python
    len(df) / 1e6   # Number of rows in millions
<div class=md_output>

    121.232833
</div>


    ::Python
    df.head()


<div class="md_output">
<table class="dataframe" border="1">
  <thead>
    <tr>
      <th></th>
      <th>Year</th>
      <th>Month</th>
      <th>DayOfWeek</th>
      <th>UniqueCarrier</th>
      <th>Origin</th>
      <th>Dest</th>
      <th>delayed</th>
      <th>hour</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>1987</td>
      <td>10</td>
      <td>3</td>
      <td>PS</td>
      <td>SAN</td>
      <td>SFO</td>
      <td>0</td>
      <td>7</td>
    </tr>
    <tr>
      <th>1</th>
      <td>1987</td>
      <td>10</td>
      <td>4</td>
      <td>PS</td>
      <td>SAN</td>
      <td>SFO</td>
      <td>0</td>
      <td>7</td>
    </tr>
    <tr>
      <th>2</th>
      <td>1987</td>
      <td>10</td>
      <td>6</td>
      <td>PS</td>
      <td>SAN</td>
      <td>SFO</td>
      <td>0</td>
      <td>7</td>
    </tr>
    <tr>
      <th>3</th>
      <td>1987</td>
      <td>10</td>
      <td>7</td>
      <td>PS</td>
      <td>SAN</td>
      <td>SFO</td>
      <td>0</td>
      <td>7</td>
    </tr>
    <tr>
      <th>4</th>
      <td>1987</td>
      <td>10</td>
      <td>1</td>
      <td>PS</td>
      <td>SAN</td>
      <td>SFO</td>
      <td>1</td>
      <td>7</td>
    </tr>
  </tbody>
</table>
</div>


So we have roughly 121 million rows, each with 8 columns each. Looking at the
columns you can see that each variable is categorical in nature, which will be
important later on.


## Exploratory Plotting

Now that we have the data loaded into memory on the cluster, most dataframe
computations will run *much* faster. Lets do some exploratory plotting to see
the relationship between certain features and our target variable.

    ::Python
    # Define some aggregations to plot
    aggregations = (df.groupby('Year').delayed.mean(),
                    df.groupby('Month').delayed.mean(),
                    df.groupby('hour').delayed.mean(),
                    df.groupby('UniqueCarrier').delayed.mean().nlargest(15))

    # Compute them all in a single pass over the data
    (delayed_by_year,
    delayed_by_month,
    delayed_by_hour,
    delayed_by_carrier) = dask.compute(*aggregations)


Plotting these series with bokeh gives:


<head>
    <meta charset="utf-8">
    <title>grouped</title>

<link rel="stylesheet" href="https://cdn.pydata.org/bokeh/release/bokeh-0.12.0.min.css" type="text/css" />

<script type="text/javascript" src="https://cdn.pydata.org/bokeh/release/bokeh-0.12.0.min.js"></script>
<script type="text/javascript">
Bokeh.set_log_level("info");
</script>
<style>
    html {
    width: 100%;
    height: 100%;
    }
    body {
    width: 90%;
    height: 100%;
    margin: auto;
    }
</style>
</head>
<body>

<div class="bk-root">
    <div class="plotdiv" id="e6baeda8-a427-41ff-947e-e4b92df15404"></div>
</div>

<script type="text/javascript">
    Bokeh.$(function() {
    var docs_json = {"ab14befb-bed9-47aa-87a7-4bdd0fd9ade2":{"roots":{"references":[{"attributes":{"fill_alpha":{"value":0.1},"fill_color":{"value":"#1f77b4"},"line_alpha":{"value":0.1},"line_color":{"value":"#1f77b4"},"size":{"units":"screen","value":8},"x":{"field":"x"},"y":{"field":"y"}},"id":"cb577bce-29b3-4ae5-afa4-dcbcd70a177c","type":"Circle"},{"attributes":{"callback":null},"id":"60591746-08e2-40e0-b257-a9de60cad7fd","type":"DataRange1d"},{"attributes":{},"id":"a2f0e78e-ad80-4a52-b1cc-780b2fed7879","type":"BasicTicker"},{"attributes":{"axis_label":"Fraction Delayed","formatter":{"id":"2af3f5fb-092a-48bc-ad97-22fde7292bd4","type":"BasicTickFormatter"},"plot":{"id":"d0704160-8b75-4c38-b4ee-781d8aa9e301","subtype":"Figure","type":"Plot"},"ticker":{"id":"5825de8c-2bd6-471a-a8fb-fa65b596879f","type":"BasicTicker"}},"id":"3019cc97-53cd-47b9-8731-1c94d6c3ba4d","type":"LinearAxis"},{"attributes":{"callback":null},"id":"cec6fdc7-b471-4056-b124-0275d3c9fd6b","type":"DataRange1d"},{"attributes":{},"id":"6729f770-6e3a-44ed-a3a8-63627849dde9","type":"ToolEvents"},{"attributes":{"plot":null,"text":"Delayed flights per Year"},"id":"f0a5f1d4-f44b-4c42-b5ef-20b852cfc780","type":"Title"},{"attributes":{"data_source":{"id":"89abe4ad-5d1c-4be8-a175-ef61dcdf8019","type":"ColumnDataSource"},"glyph":{"id":"73d21d78-3fee-4b8e-ad98-a1bfb557a385","type":"Circle"},"hover_glyph":null,"nonselection_glyph":{"id":"f5d720a0-8ca2-4a12-a5bf-0a4726642330","type":"Circle"},"selection_glyph":null},"id":"459d8be1-8d0a-4f92-b31d-f672c3d9890f","type":"GlyphRenderer"},{"attributes":{},"id":"61122da6-f606-4c1a-b740-73ca3eeb911e","type":"CategoricalTicker"},{"attributes":{"axis_label":"Fraction Delayed","formatter":{"id":"933786ac-40f5-46fb-b099-0702def90aab","type":"BasicTickFormatter"},"plot":{"id":"261f6b09-6d7a-46b3-923a-5791893de9ba","subtype":"Figure","type":"Plot"},"ticker":{"id":"ed38d0f6-a53f-4ea2-a1aa-ba25422c084d","type":"BasicTicker"}},"id":"d8613324-cce8-47f5-9592-8923dffeae5b","type":"LinearAxis"},{"attributes":{"dimension":1,"plot":{"id":"d0704160-8b75-4c38-b4ee-781d8aa9e301","subtype":"Figure","type":"Plot"},"ticker":{"id":"5825de8c-2bd6-471a-a8fb-fa65b596879f","type":"BasicTicker"}},"id":"6357b3af-2d2a-47ff-b7fc-96e27486ffa4","type":"Grid"},{"attributes":{"children":[{"id":"261f6b09-6d7a-46b3-923a-5791893de9ba","subtype":"Figure","type":"Plot"},{"id":"6f3bb9c5-84ee-40ee-8143-250079b8aba7","subtype":"Figure","type":"Plot"}],"sizing_mode":"scale_width"},"id":"4ffb5bf3-e7c6-4dde-8467-47d4b308330c","type":"Row"},{"attributes":{"axis_label":"Year","formatter":{"id":"7519faa1-6457-401b-8eaa-93382b9b0b75","type":"CategoricalTickFormatter"},"major_label_orientation":0.628,"plot":{"id":"261f6b09-6d7a-46b3-923a-5791893de9ba","subtype":"Figure","type":"Plot"},"ticker":{"id":"4ece69f3-da1c-46d5-bfa0-f82e1c3f2608","type":"CategoricalTicker"}},"id":"3543f3ac-c2e1-4709-a4ff-94b36a4f3926","type":"CategoricalAxis"},{"attributes":{},"id":"b347f37f-1da1-4f07-a782-9f10ca2d3110","type":"CategoricalTicker"},{"attributes":{"callback":null,"column_names":["y","x"],"data":{"x":[1,2,3,4,5,6,7,8,9,10,11,12],"y":[0.17477918374037374,0.16636326530434445,0.16063382389045794,0.13037047527360912,0.12882822605912844,0.17247882431789996,0.16632604283652996,0.1575662728800393,0.10990616413959045,0.12350199445430639,0.13662008476965967,0.20449978799243357]}},"id":"42f06a8f-756c-402d-98af-9b2e57843a34","type":"ColumnDataSource"},{"attributes":{},"id":"4ece69f3-da1c-46d5-bfa0-f82e1c3f2608","type":"CategoricalTicker"},{"attributes":{"axis_label":"Carrier","formatter":{"id":"3e11eb37-4fc4-4d56-946d-b069d0708ab4","type":"CategoricalTickFormatter"},"plot":{"id":"07707fe8-7745-4cb5-a0b0-e55edc39a325","subtype":"Figure","type":"Plot"},"ticker":{"id":"b347f37f-1da1-4f07-a782-9f10ca2d3110","type":"CategoricalTicker"}},"id":"b65a403c-53d0-4bcd-a4af-1c3997f59b35","type":"CategoricalAxis"},{"attributes":{"axis_label":"Fraction Delayed","formatter":{"id":"ee04c846-b004-4d0b-b536-44f193914bb9","type":"BasicTickFormatter"},"plot":{"id":"6f3bb9c5-84ee-40ee-8143-250079b8aba7","subtype":"Figure","type":"Plot"},"ticker":{"id":"02d42965-ff23-46ec-b93d-b973c076d7f4","type":"BasicTicker"}},"id":"865d8b4e-a7c2-4d87-a903-01b76b2f9439","type":"LinearAxis"},{"attributes":{"plot":null,"text":"Delayed flights by Carrier"},"id":"5150d714-bb1a-4344-9aec-b00bd46ebc92","type":"Title"},{"attributes":{"callback":null,"column_names":["y","x"],"data":{"x":[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24],"y":[0.15991832637763304,0.11846077401935048,0.07655757834605734,0.06536203522504892,0.06556463595839525,0.044156435605988725,0.04935413626862435,0.06463941124171121,0.0873985873202963,0.1068911370253868,0.12031073633888852,0.13427418148493978,0.14089783489666582,0.15174348317556038,0.16719321836015744,0.18247333606792346,0.19372800225256934,0.2119529662913611,0.2196567622695267,0.23017455775439724,0.23256460089117165,0.22465644489691952,0.1883157996180982,0.16810620757731984]}},"id":"4687d174-f91b-442f-bfa6-7a7301397032","type":"ColumnDataSource"},{"attributes":{"grid_line_color":{"value":null},"plot":{"id":"261f6b09-6d7a-46b3-923a-5791893de9ba","subtype":"Figure","type":"Plot"},"ticker":{"id":"4ece69f3-da1c-46d5-bfa0-f82e1c3f2608","type":"CategoricalTicker"}},"id":"52354d76-ed30-42fc-9538-0ff86055fd32","type":"Grid"},{"attributes":{"data_source":{"id":"f180cfda-e23a-4bdd-9c48-4c0c23ca7f11","type":"ColumnDataSource"},"glyph":{"id":"b2f3563c-fc28-4e2f-8261-88bf7f199b51","type":"Circle"},"hover_glyph":null,"nonselection_glyph":{"id":"27d5f47b-b4c4-4bc0-a134-dd88f1db0902","type":"Circle"},"selection_glyph":null},"id":"1d90a670-d8df-4009-9139-aa41fd708ffd","type":"GlyphRenderer"},{"attributes":{"plot":null,"text":"Delayed flights by Hour"},"id":"f39e8779-a228-402c-af3e-31443a26395c","type":"Title"},{"attributes":{},"id":"e3f10d53-fe5e-45fe-88eb-1b66903c4a18","type":"BasicTickFormatter"},{"attributes":{"data_source":{"id":"4687d174-f91b-442f-bfa6-7a7301397032","type":"ColumnDataSource"},"glyph":{"id":"349e769a-781c-436f-89a7-03210ab903e3","type":"Circle"},"hover_glyph":null,"nonselection_glyph":{"id":"cb577bce-29b3-4ae5-afa4-dcbcd70a177c","type":"Circle"},"selection_glyph":null},"id":"d31d284a-a3f2-4800-bd8c-8896c448f3b2","type":"GlyphRenderer"},{"attributes":{"active_drag":"auto","active_scroll":"auto","active_tap":"auto"},"id":"1a36643c-be36-4db5-9734-00f5d600b744","type":"Toolbar"},{"attributes":{"plot":null,"text":"Delayed flights per Month"},"id":"fe9092a6-4003-4e48-a6a4-6445dca3785a","type":"Title"},{"attributes":{},"id":"66ef0c7e-6fc5-4131-8a33-d0044ed48304","type":"ToolEvents"},{"attributes":{"callback":null},"id":"b5b2e061-d208-4463-a363-b6551d94ab15","type":"DataRange1d"},{"attributes":{},"id":"3e11eb37-4fc4-4d56-946d-b069d0708ab4","type":"CategoricalTickFormatter"},{"attributes":{},"id":"7926eb29-4c57-40d5-af88-ace8f948d807","type":"CategoricalTickFormatter"},{"attributes":{"axis_label":"Hour","formatter":{"id":"e9fdbc15-fcb5-40e3-bb4f-841d11f0a557","type":"CategoricalTickFormatter"},"plot":{"id":"d0704160-8b75-4c38-b4ee-781d8aa9e301","subtype":"Figure","type":"Plot"},"ticker":{"id":"61122da6-f606-4c1a-b740-73ca3eeb911e","type":"CategoricalTicker"}},"id":"adc42a44-a4e1-41b3-b272-daf7d2d6d37f","type":"CategoricalAxis"},{"attributes":{"active_drag":"auto","active_scroll":"auto","active_tap":"auto"},"id":"68139999-a154-4f88-86ae-d7b7d99855c1","type":"Toolbar"},{"attributes":{},"id":"fb032f05-cb0e-4a02-8b27-b172fb214255","type":"CategoricalTicker"},{"attributes":{"axis_label":"Month","formatter":{"id":"7926eb29-4c57-40d5-af88-ace8f948d807","type":"CategoricalTickFormatter"},"plot":{"id":"6f3bb9c5-84ee-40ee-8143-250079b8aba7","subtype":"Figure","type":"Plot"},"ticker":{"id":"fb032f05-cb0e-4a02-8b27-b172fb214255","type":"CategoricalTicker"}},"id":"2d768595-6fc4-4fba-a11e-dfd70bde56ec","type":"CategoricalAxis"},{"attributes":{},"id":"5825de8c-2bd6-471a-a8fb-fa65b596879f","type":"BasicTicker"},{"attributes":{},"id":"e9fdbc15-fcb5-40e3-bb4f-841d11f0a557","type":"CategoricalTickFormatter"},{"attributes":{},"id":"7519faa1-6457-401b-8eaa-93382b9b0b75","type":"CategoricalTickFormatter"},{"attributes":{"dimension":1,"plot":{"id":"261f6b09-6d7a-46b3-923a-5791893de9ba","subtype":"Figure","type":"Plot"},"ticker":{"id":"ed38d0f6-a53f-4ea2-a1aa-ba25422c084d","type":"BasicTicker"}},"id":"e85339ea-ca13-4540-9607-6a211885b9b9","type":"Grid"},{"attributes":{"fill_color":{"value":"purple"},"line_color":{"value":"purple"},"size":{"units":"screen","value":8},"x":{"field":"x"},"y":{"field":"y"}},"id":"349e769a-781c-436f-89a7-03210ab903e3","type":"Circle"},{"attributes":{},"id":"ee04c846-b004-4d0b-b536-44f193914bb9","type":"BasicTickFormatter"},{"attributes":{"dimension":1,"plot":{"id":"6f3bb9c5-84ee-40ee-8143-250079b8aba7","subtype":"Figure","type":"Plot"},"ticker":{"id":"02d42965-ff23-46ec-b93d-b973c076d7f4","type":"BasicTicker"}},"id":"e82dd94b-136f-42fc-9d0f-e66287779533","type":"Grid"},{"attributes":{},"id":"02d42965-ff23-46ec-b93d-b973c076d7f4","type":"BasicTicker"},{"attributes":{"below":[{"id":"b65a403c-53d0-4bcd-a4af-1c3997f59b35","type":"CategoricalAxis"}],"left":[{"id":"e37831f2-b33b-4f80-9632-ce368721dc46","type":"LinearAxis"}],"plot_height":300,"renderers":[{"id":"b65a403c-53d0-4bcd-a4af-1c3997f59b35","type":"CategoricalAxis"},{"id":"7e894e33-f57e-4a7d-b944-bd681521d24e","type":"Grid"},{"id":"e37831f2-b33b-4f80-9632-ce368721dc46","type":"LinearAxis"},{"id":"01498f02-3cb4-4413-8e4c-539ae2a1a804","type":"Grid"},{"id":"1d90a670-d8df-4009-9139-aa41fd708ffd","type":"GlyphRenderer"}],"sizing_mode":"scale_width","title":{"id":"5150d714-bb1a-4344-9aec-b00bd46ebc92","type":"Title"},"tool_events":{"id":"6729f770-6e3a-44ed-a3a8-63627849dde9","type":"ToolEvents"},"toolbar":{"id":"68139999-a154-4f88-86ae-d7b7d99855c1","type":"Toolbar"},"toolbar_location":null,"x_range":{"id":"9d6a7c56-62ef-429e-a7ce-3d91c29f2678","type":"FactorRange"},"y_range":{"id":"b5b2e061-d208-4463-a363-b6551d94ab15","type":"DataRange1d"}},"id":"07707fe8-7745-4cb5-a0b0-e55edc39a325","subtype":"Figure","type":"Plot"},{"attributes":{"fill_color":{"value":"purple"},"line_color":{"value":"purple"},"size":{"units":"screen","value":8},"x":{"field":"x"},"y":{"field":"y"}},"id":"65806ba2-4a78-4428-9739-8a816b9da661","type":"Circle"},{"attributes":{"fill_color":{"value":"purple"},"line_color":{"value":"purple"},"size":{"units":"screen","value":8},"x":{"field":"x"},"y":{"field":"y"}},"id":"73d21d78-3fee-4b8e-ad98-a1bfb557a385","type":"Circle"},{"attributes":{"active_drag":"auto","active_scroll":"auto","active_tap":"auto"},"id":"122132de-cb2f-4cdc-84bd-53b5cdb844d3","type":"Toolbar"},{"attributes":{},"id":"933786ac-40f5-46fb-b099-0702def90aab","type":"BasicTickFormatter"},{"attributes":{"callback":null,"factors":["87","88","89","90","91","92","93","94","95","96","97","98","99","00","01","02","03","04","05","06","07","08"]},"id":"9e835a87-e9dd-4270-842a-eeb52f33f53d","type":"FactorRange"},{"attributes":{},"id":"704176df-a80c-4b8d-8f95-e0b1fbae20da","type":"ToolEvents"},{"attributes":{"fill_alpha":{"value":0.1},"fill_color":{"value":"#1f77b4"},"line_alpha":{"value":0.1},"line_color":{"value":"#1f77b4"},"size":{"units":"screen","value":8},"x":{"field":"x"},"y":{"field":"y"}},"id":"0e22a15d-ca6b-4a3a-815f-3f1d2fe238e7","type":"Circle"},{"attributes":{"grid_line_color":{"value":null},"plot":{"id":"07707fe8-7745-4cb5-a0b0-e55edc39a325","subtype":"Figure","type":"Plot"},"ticker":{"id":"b347f37f-1da1-4f07-a782-9f10ca2d3110","type":"CategoricalTicker"}},"id":"7e894e33-f57e-4a7d-b944-bd681521d24e","type":"Grid"},{"attributes":{"callback":null,"column_names":["y","x"],"data":{"x":[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22],"y":[0.14727727082415928,0.1205289354500534,0.1501761111004855,0.1245522843534508,0.10623095231472836,0.1033825787243956,0.1112950080787825,0.12035496394897394,0.14811356252375596,0.17591601867502438,0.1497309035618583,0.1567940381038019,0.1648837747249363,0.19563185314973533,0.15684426719604114,0.12805884350553262,0.1222198719882713,0.1592164436458234,0.17171928220120095,0.19270745192157024,0.20686689428968277,0.1856986022513771]}},"id":"89abe4ad-5d1c-4be8-a175-ef61dcdf8019","type":"ColumnDataSource"},{"attributes":{"grid_line_color":{"value":null},"plot":{"id":"d0704160-8b75-4c38-b4ee-781d8aa9e301","subtype":"Figure","type":"Plot"},"ticker":{"id":"61122da6-f606-4c1a-b740-73ca3eeb911e","type":"CategoricalTicker"}},"id":"045f1b15-40d5-46de-8974-0c4b486a2bf4","type":"Grid"},{"attributes":{"callback":null,"factors":["0","1","2","3","4","5","6","7","8","9","10","11","12","13","14","15","16","17","18","19","20","21","22","23"]},"id":"de6ad55a-90a2-4d76-8bfc-56fd4c1e1feb","type":"FactorRange"},{"attributes":{"callback":null,"factors":["1","2","3","4","5","6","7","8","9","10","11","12"]},"id":"8b5c24bf-363f-41de-a8f6-e3075349b22b","type":"FactorRange"},{"attributes":{"grid_line_color":{"value":null},"plot":{"id":"6f3bb9c5-84ee-40ee-8143-250079b8aba7","subtype":"Figure","type":"Plot"},"ticker":{"id":"fb032f05-cb0e-4a02-8b27-b172fb214255","type":"CategoricalTicker"}},"id":"87fd467d-36e3-4577-b997-de3701d27677","type":"Grid"},{"attributes":{"active_drag":"auto","active_scroll":"auto","active_tap":"auto"},"id":"22f8377e-a557-4cfa-810c-fba362a4198d","type":"Toolbar"},{"attributes":{},"id":"ed38d0f6-a53f-4ea2-a1aa-ba25422c084d","type":"BasicTicker"},{"attributes":{"below":[{"id":"2d768595-6fc4-4fba-a11e-dfd70bde56ec","type":"CategoricalAxis"}],"left":[{"id":"865d8b4e-a7c2-4d87-a903-01b76b2f9439","type":"LinearAxis"}],"plot_height":300,"renderers":[{"id":"2d768595-6fc4-4fba-a11e-dfd70bde56ec","type":"CategoricalAxis"},{"id":"87fd467d-36e3-4577-b997-de3701d27677","type":"Grid"},{"id":"865d8b4e-a7c2-4d87-a903-01b76b2f9439","type":"LinearAxis"},{"id":"e82dd94b-136f-42fc-9d0f-e66287779533","type":"Grid"},{"id":"475ca8a1-e7bd-43e3-976f-28fcf5757a64","type":"GlyphRenderer"}],"sizing_mode":"scale_width","title":{"id":"fe9092a6-4003-4e48-a6a4-6445dca3785a","type":"Title"},"tool_events":{"id":"18efec75-2c60-47ab-b823-29e23b582e41","type":"ToolEvents"},"toolbar":{"id":"1a36643c-be36-4db5-9734-00f5d600b744","type":"Toolbar"},"toolbar_location":null,"x_range":{"id":"8b5c24bf-363f-41de-a8f6-e3075349b22b","type":"FactorRange"},"y_range":{"id":"8a5f7393-f1d3-468c-9943-29a4fcdc67c1","type":"DataRange1d"}},"id":"6f3bb9c5-84ee-40ee-8143-250079b8aba7","subtype":"Figure","type":"Plot"},{"attributes":{"callback":null,"factors":["EV","YV","B6","FL","MQ","DH","OH","WN","PS","UA","PI","AS","XE","F9","9E"]},"id":"9d6a7c56-62ef-429e-a7ce-3d91c29f2678","type":"FactorRange"},{"attributes":{"children":[{"id":"d0704160-8b75-4c38-b4ee-781d8aa9e301","subtype":"Figure","type":"Plot"},{"id":"07707fe8-7745-4cb5-a0b0-e55edc39a325","subtype":"Figure","type":"Plot"}],"sizing_mode":"scale_width"},"id":"f9e119c6-c34f-48e3-8db3-6b5aa3a17557","type":"Row"},{"attributes":{"fill_alpha":{"value":0.1},"fill_color":{"value":"#1f77b4"},"line_alpha":{"value":0.1},"line_color":{"value":"#1f77b4"},"size":{"units":"screen","value":8},"x":{"field":"x"},"y":{"field":"y"}},"id":"27d5f47b-b4c4-4bc0-a134-dd88f1db0902","type":"Circle"},{"attributes":{"fill_alpha":{"value":0.1},"fill_color":{"value":"#1f77b4"},"line_alpha":{"value":0.1},"line_color":{"value":"#1f77b4"},"size":{"units":"screen","value":8},"x":{"field":"x"},"y":{"field":"y"}},"id":"f5d720a0-8ca2-4a12-a5bf-0a4726642330","type":"Circle"},{"attributes":{"children":[{"id":"4ffb5bf3-e7c6-4dde-8467-47d4b308330c","type":"Row"},{"id":"f9e119c6-c34f-48e3-8db3-6b5aa3a17557","type":"Row"}],"sizing_mode":"scale_width"},"id":"45d1bfbe-d900-41ed-ac95-f66307ac71dc","type":"Column"},{"attributes":{},"id":"18efec75-2c60-47ab-b823-29e23b582e41","type":"ToolEvents"},{"attributes":{"axis_label":"Fraction Delayed","formatter":{"id":"e3f10d53-fe5e-45fe-88eb-1b66903c4a18","type":"BasicTickFormatter"},"plot":{"id":"07707fe8-7745-4cb5-a0b0-e55edc39a325","subtype":"Figure","type":"Plot"},"ticker":{"id":"a2f0e78e-ad80-4a52-b1cc-780b2fed7879","type":"BasicTicker"}},"id":"e37831f2-b33b-4f80-9632-ce368721dc46","type":"LinearAxis"},{"attributes":{"callback":null},"id":"8a5f7393-f1d3-468c-9943-29a4fcdc67c1","type":"DataRange1d"},{"attributes":{"callback":null,"column_names":["y","x"],"data":{"x":[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15],"y":[0.23563452312421862,0.20921614475579375,0.20125748525390955,0.19776506155902687,0.194105888818347,0.18770672752287698,0.1767972449418855,0.17013937172113014,0.16971842941333398,0.16902111842531067,0.16784405934012833,0.1662145093747751,0.1649762006282686,0.15783616710871376,0.14908077884358917]}},"id":"f180cfda-e23a-4bdd-9c48-4c0c23ca7f11","type":"ColumnDataSource"},{"attributes":{"below":[{"id":"3543f3ac-c2e1-4709-a4ff-94b36a4f3926","type":"CategoricalAxis"}],"left":[{"id":"d8613324-cce8-47f5-9592-8923dffeae5b","type":"LinearAxis"}],"plot_height":300,"renderers":[{"id":"3543f3ac-c2e1-4709-a4ff-94b36a4f3926","type":"CategoricalAxis"},{"id":"52354d76-ed30-42fc-9538-0ff86055fd32","type":"Grid"},{"id":"d8613324-cce8-47f5-9592-8923dffeae5b","type":"LinearAxis"},{"id":"e85339ea-ca13-4540-9607-6a211885b9b9","type":"Grid"},{"id":"459d8be1-8d0a-4f92-b31d-f672c3d9890f","type":"GlyphRenderer"}],"sizing_mode":"scale_width","title":{"id":"f0a5f1d4-f44b-4c42-b5ef-20b852cfc780","type":"Title"},"tool_events":{"id":"704176df-a80c-4b8d-8f95-e0b1fbae20da","type":"ToolEvents"},"toolbar":{"id":"122132de-cb2f-4cdc-84bd-53b5cdb844d3","type":"Toolbar"},"toolbar_location":null,"x_range":{"id":"9e835a87-e9dd-4270-842a-eeb52f33f53d","type":"FactorRange"},"y_range":{"id":"60591746-08e2-40e0-b257-a9de60cad7fd","type":"DataRange1d"}},"id":"261f6b09-6d7a-46b3-923a-5791893de9ba","subtype":"Figure","type":"Plot"},{"attributes":{"fill_color":{"value":"purple"},"line_color":{"value":"purple"},"size":{"units":"screen","value":8},"x":{"field":"x"},"y":{"field":"y"}},"id":"b2f3563c-fc28-4e2f-8261-88bf7f199b51","type":"Circle"},{"attributes":{"dimension":1,"plot":{"id":"07707fe8-7745-4cb5-a0b0-e55edc39a325","subtype":"Figure","type":"Plot"},"ticker":{"id":"a2f0e78e-ad80-4a52-b1cc-780b2fed7879","type":"BasicTicker"}},"id":"01498f02-3cb4-4413-8e4c-539ae2a1a804","type":"Grid"},{"attributes":{"data_source":{"id":"42f06a8f-756c-402d-98af-9b2e57843a34","type":"ColumnDataSource"},"glyph":{"id":"65806ba2-4a78-4428-9739-8a816b9da661","type":"Circle"},"hover_glyph":null,"nonselection_glyph":{"id":"0e22a15d-ca6b-4a3a-815f-3f1d2fe238e7","type":"Circle"},"selection_glyph":null},"id":"475ca8a1-e7bd-43e3-976f-28fcf5757a64","type":"GlyphRenderer"},{"attributes":{"below":[{"id":"adc42a44-a4e1-41b3-b272-daf7d2d6d37f","type":"CategoricalAxis"}],"left":[{"id":"3019cc97-53cd-47b9-8731-1c94d6c3ba4d","type":"LinearAxis"}],"plot_height":300,"renderers":[{"id":"adc42a44-a4e1-41b3-b272-daf7d2d6d37f","type":"CategoricalAxis"},{"id":"045f1b15-40d5-46de-8974-0c4b486a2bf4","type":"Grid"},{"id":"3019cc97-53cd-47b9-8731-1c94d6c3ba4d","type":"LinearAxis"},{"id":"6357b3af-2d2a-47ff-b7fc-96e27486ffa4","type":"Grid"},{"id":"d31d284a-a3f2-4800-bd8c-8896c448f3b2","type":"GlyphRenderer"}],"sizing_mode":"scale_width","title":{"id":"f39e8779-a228-402c-af3e-31443a26395c","type":"Title"},"tool_events":{"id":"66ef0c7e-6fc5-4131-8a33-d0044ed48304","type":"ToolEvents"},"toolbar":{"id":"22f8377e-a557-4cfa-810c-fba362a4198d","type":"Toolbar"},"toolbar_location":null,"x_range":{"id":"de6ad55a-90a2-4d76-8bfc-56fd4c1e1feb","type":"FactorRange"},"y_range":{"id":"cec6fdc7-b471-4056-b124-0275d3c9fd6b","type":"DataRange1d"}},"id":"d0704160-8b75-4c38-b4ee-781d8aa9e301","subtype":"Figure","type":"Plot"},{"attributes":{},"id":"2af3f5fb-092a-48bc-ad97-22fde7292bd4","type":"BasicTickFormatter"}],"root_ids":["45d1bfbe-d900-41ed-ac95-f66307ac71dc"]},"title":"Bokeh Application","version":"0.12.0"}};
    var render_items = [{"docid":"ab14befb-bed9-47aa-87a7-4bdd0fd9ade2","elementid":"e6baeda8-a427-41ff-947e-e4b92df15404","modelid":"45d1bfbe-d900-41ed-ac95-f66307ac71dc"}];

    Bokeh.embed.embed_items(docs_json, render_items);
});
</script>
</body>


The hour one is especially interesting, as it shows an increase in frequency of
delays over the course of each day. This is possibly due to a cascading effect,
as earlier delayed flights cause problems for later flights waiting on the
plane/gate.


## Extract Features

As we saw above, all of our columns are categorical in nature. To make best
use of these, we need to "one-hot encode" our target variables. Scikit-learn
provides [a builtin
class](http://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.OneHotEncoder.html)
for doing this, but it doesn't play as well with dataframe inputs. Instead of
making a new class, we can do the same operation using some simple functions
and the [dask delayed](http://dask.pydata.org/en/latest/delayed.html)
interface.

Here we define a function `one_hot_encode` to transform a given
`pandas.DataFrame` into a sparse matrix, given a mapping of categories for each
column. We've decorated the function with `dask.delayed`, which makes the
function return a lazy object instead of computing immediately.

    ::Python
    import pandas as pd
    import numpy as np
    from dask import delayed
    from scipy import sparse

    def one_hot_encode_series(s, categories, dtype='f8'):
        """Transform a pandas.Series into a sparse matrix by one-hot-encoding
        for the given `categories`"""
        cat = pd.Categorical(s, np.asarray(categories))
        codes = cat.codes
        n_features = len(cat.categories)
        n_samples = codes.size
        mask = codes != -1
        if np.any(~mask):
            raise ValueError("unknown categorical features present %s "
                            "during transform." % np.unique(s[~mask]))
        row_indices = np.arange(n_samples, dtype=np.int32)
        col_indices = codes
        data = np.ones(row_indices.size)
        return sparse.coo_matrix((data, (row_indices, col_indices)),
                                shape=(n_samples, n_features),
                                dtype=dtype).tocsr()


    @delayed(pure=True)
    def one_hot_encode(df, categories, dtype='f8'):
        """One-hot-encode a pandas.DataFrame.

        Parameters
        ----------
        df : pandas.DataFrame
        categories : dict
            A mapping of column name to an sequence of categories for the column.
        dtype : str, optional
            The dtype of the output array. Default is 'float64'.
        """
        arrs = [one_hot_encode_series(df[col], cats, dtype=dtype)
                for col, cats in sorted(categories.items())]
        return sparse.hstack(arrs).tocsr()


To use this function, we need to get a `dict` mapping column names to their
categorical values. This isn't ideal, as it requires a complete pass over the
data before transformation. Since the data is already in memory though, this is
fairly quick to do:

    ::Python
    # Extract categories for each feature
    categories = dict(Year=np.arange(1987, 2009),
                      Month=np.arange(1, 13),
                      DayOfWeek=np.arange(1, 8),
                      hour=np.arange(24),
                      UniqueCarrier=df.UniqueCarrier.unique(),
                      Origin=df.Origin.unique(),
                      Dest=df.Dest.unique())

    # Compute all the categories in one pass
    categories = delayed(categories).compute()


Finally, we can build up our feature and target matrices, as two
`dklearn.matrix.Matrix` objects.

    ::Python
    import dklearn.matrix as dm

    # Convert the series `delayed` into a `Matrix`
    y = dm.from_series(df.delayed)

    # `to_delayed` returns a list of `dask.Delayed` objects, each representing
    # one partition in the total `dask.dataframe`
    chunks = df.to_delayed()

    # Apply `one_hot_encode` to each chunk, and then convert all the
    # chunks into a `Matrix`
    X = dm.from_delayed([one_hot_encode(x, categories) for x in chunks],
                        dtype='f8')
    X, y
<div class=md_output>

    (dklearn.matrix<matrix-..., npartitions=104, dtype=float64>,
     dklearn.matrix<matrix-..., npartitions=104, dtype=int64>)
</div>


## Extract train-test splits

Now that we have our feature and target matrices, we're almost ready to start
training an estimator. The last thing we need to do is hold back some of the
data for testing later on. To do that, we can use the `train_test_split`
function, which mirrors the [scikit-learn function of the same
name](http://scikit-learn.org/stable/modules/generated/sklearn.cross_validation.train_test_split.html).
We'll hold back `20%` of the rows:

    ::Python
    from dklearn.cross_validation import train_test_split

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)


## Create an estimator

As discussed in [the previous post]({filename}/dask_learn_part_2.md),
dask-learn contains several parallelization patterns for wrapping scikit-learn
estimators. These make it easy to use with any estimator that matches the
scikit-learn standard interface. Here we'll wrap a `SGDClassifier` with the
`Averaged` wrapper. This will fit the classifier on each partition of the data,
and then average the resulting coefficients to produce a final estimator.

    ::Python
    from dklearn import Averaged
    from sklearn.linear_model import SGDClassifier

    est = Averaged(SGDClassifier())


## Distributed grid search

The `SGDClassifier` also takes several hyperparameters, we'll do a grid search
across a few of them to try and pick the best combination. Note that the
dask-learn version of `GridSearchCV` mirrors the interface of the scikit-learn
equivalent. We'll also pass in an instance of `RandomSplit` to use for
cross-validation, instead of the default `KFold`. We do this because the
samples are ordered approximately chronologically, and `KFold` would result in
training data with potentially missing years.


    ::Python
    from dklearn.cross_validation import RandomSplit
    from dklearn.grid_search import GridSearchCV

    grid = {'alpha': [0.0001, 0.001],
            'loss': ['log', 'hinge']}

    search = GridSearchCV(est, grid,
                          cv=RandomSplit(n_iter=3, test_size=0.2))


Finally we can call `fit` and perform the grid search. As discussed in [In part
1]({filename}/dask_learn_part_1.md), `GridSearchCV` isn't lazy due to some
complications with the scikit-learn api, so this call to `fit` runs
immediately.

    ::Python
    search.fit(X_train, y_train)

What's happening here is:

- An estimator is created for each parameter combination and test-train set
- Each estimator is then fit on its corresponding set of training data (using
  the `Averaged` parallelization pattern)
- Each estimator is then scored on its corresponding set of testing data
- The best set of parameters will then be chosen based on these scores
- Finally, a new estimator is then fit on *all* of the data, using the best parameters

Note that this is all run in parallel, distributed across the cluster. Thanks
to the [slick web
interface](http://distributed.readthedocs.io/en/latest/web.html), you can watch
it compute. This takes a couple minutes, here's a gif of just the start:

<img src="images/distributed_grid_search_webui.gif" alt="Distributed Web UI" style="width:100%">


Once all the computation is done, we can see the best score and parameters by
checking the `best_score_` and `best_params_` attributes (continuing to mirror
the scikit-learn interface):

    ::Python
    search.best_score_
<div class=md_output>

    0.83144082308054479
</div>

    ::Python
    search.best_params_
<div class=md_output>

    {'alpha': 0.0001, 'loss': 'hinge'}
</div>

So we got `~83%` accuracy on predicting if a flight was delayed based on these
features. The best estimator (after refitting on all of the training data) is
stored in the `best_estimator_` attribute:

    ::Python
    search.best_estimator_
<div class=md_output>

    SGDClassifier(alpha=0.0001, average=False, class_weight=None, epsilon=0.1,
        eta0=0.0, fit_intercept=True, l1_ratio=0.15,
        learning_rate='optimal', loss='hinge', n_iter=5, n_jobs=1,
        penalty='l2', power_t=0.5, random_state=None, shuffle=True,
        verbose=0, warm_start=False)
</div>


## Scoring the model

To evaluate our model, we can check its performance on the testing data we held
out originally. This illustrates an issue with the current design; both
`predict` and many of the `score` functions are parallelizable, but since we
don't know which one a given estimator uses in its `score` method, we can't
dispatch to a parallel implementation easily. For now, we can call `predict`
(which we can parallelize), and then compute the score directly using the
`accuracy_score` function (the default score for classifiers).

    ::Python
    from sklearn.metrics import accuracy_score

    # Call `predict` in parallel on the testing data
    y_pred = search.predict(X_test)

    # Compute the actual and predicted targets
    actual, predicted = dask.compute(y_test, y_pred)

    # Score locally
    accuracy_score(actual, predicted)
<div class=md_output>

    0.83146828311187182
</div>

So the overall accuracy score is `~83%`, roughly the same as the best score
from `GridSearchCV` above. This may sound good, but it's actually equivalent to
the strategy of predicting that no flights are delayed (roughly `83%` of all
flights leave on time).

    ::Python
    # Compute the fraction of flights that aren't delayed.
    s = df.delayed.value_counts().compute()
    s[0].astype('f8') / s.sum()
<div class=md_output>

    0.83151615151172298
</div>

I'm sure there is a better way to fit this data (I'm not a machine learning
expert). However, the point of this blogpost was to show how to use dask to
create these workflows, and I hope I was successful in that at least.

## What worked well

- Combining both model-parallelism (`GridSearchCV`) and data-parallelism
  (`Averaged`) worked fine in a familiar interface. It's nice when abstractions
  played well together.

- Operations (such as one-hot encoding) that aren't part of the built-in dask
  api were expressed using `dask.delayed` and some simple functions. This is
  nice from a user perspective, as it makes it easy to add things unique to
  your needs.

- A full analysis workflow was done on a cluster using familiar python
  interfaces. Except for a few `compute` calls here and there, everything
  should hopefully look like familiar `pandas` and `scikit-learn` code. Note
  that by [selecting a different
  scheduler](http://dask.pydata.org/en/latest/scheduler-overview.html) this
  could be done locally on a single machine as well.

- [The library](https://github.com/dask/dask-learn) demoed here is fairly short
  and easily maintainable. Only naive approaches have been implemented so far,
  but for some things the naive approaches may work well.


## What could be better

- Since scikit-learn estimators don't expose which scoring function they use in
  their `score` method, `some_dask_estimator.score` must pull all the the data
  to score onto one worker to score it. For smaller datasets this is fine, but
  for larger datasets this serialization becomes more costly.
  <p>
  One thought would be to infer the scoring function from the type of estimator
  (e.g. use `accuracy_score` for classifiers, `r2_score` for regressors,
  etc...). Dask versions of each could then be implemented, which would be *much*
  more efficient. This wouldn't work well with estimators that didn't use the
  defaults though.
  </p>

- As discussed in part 1, `GridSearchCV` isn't lazy (due to the need to support
  the `refit` keyword), while the rest of the library is. Sometimes this is
  nice, as it allows it to be a drop-in for the scikit-learn class. I'd still
  like to find a way to remove this disconnect, but haven't found a solution
  I'm happy with.


## Help

I am not a machine learning expert. Is any of this useful? Do you have
suggestions for improvements (or better yet PRs for improvements :))? Please
feel free to reach out in the comments below, or [on
github](https://github.com/dask/dask-learn).

*This work is supported by [Continuum Analytics](http://continuum.io/) and the
[XDATA](http://www.darpa.mil/program/XDATA) program as part of the [Blaze
Project](http://blaze.pydata.org/).*
