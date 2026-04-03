# sample-ocr-image.png

## Metadata

- **filename**: sample-ocr-image.png
- **content_type**: image/png
- **file_size**: 475498
- **image_format**: png
- **ocr_enabled**: True
- **ocr_language**: en
- **width**: 1239
- **height**: 1752
- **source_path**: /home/llawliet/Ignisia-MIT/examples/sample-ocr-image.png
- **num_pages**: 1

## Sections

### Image Page 1

    LLaMA: Open and Efficient Foundation Language Models


    Hugo Touvron; Thibaut Lavril; Gautier Izacard; Xavier Martinet
Marie-Anne Lachaux, Timothee Lacroix, Baptiste Roziére, Naman Goyal
    Eric Hambro, Faisal Azhar, Aurelien Rodriguez, Armand Joulin
    Edouard Grave; Guillaume Lample*

                              Meta Al


                  Abstract                                             performance, a smaller one   trained  longer  will
              We introduce LLaMA, a collection of founda-              ultimately be cheaper at inference.  For instance,
              tion language models ranging from 7B to 65B              although Hoffmann.  et al.         2022 recommends
              parameters.     We train our models on trillions         training a 10B model on 200B tokens,       we find
              of tokens, and show that it is possible to train         that the performance of a 7B model continues to
     S        state-of-the-art models using     publicly  avail-       improve even after 1T tokens.
    AN        able datasets    exclusively, without  resorting
    LO        to proprietary   and   inaccessible datasets. In           The focus of this work is to  train a series  of
              particular, LLaMA-13B   outperforms        GPT-3         language models that achieve the best possible per-
              (175B)   on most    benchmarks,     and     LLaMA-       formance at various inference budgets, by training
              os competitive     Wit                      models       on more tokens than what is typically used.    The
    —         all our      0 the research community!                   resulting models, called LLaMA,     ranges from 7B
                                                                       to 65B parameters with competitive performance
     O   1    Introduction                                             compared to the best existing LLMs.  For instance,
                                                                       LLaMA-13B outperforms GPT-3 on most bench-
    QO   Large Languages Models (LLMs) trained on mas-                 marks, despite being 10x smaller. We believe that
    ed   sive corpora of texts have shown their ability to per-        (his    model will help democratize the access and
     —   form new tasks from textual instructions or from a            study of LLMs, since it can be run on a single GPU.
     >   few examples (Brown et al., 2020). These few-shot              A¢ the higher-end of the scale, our 65B-parameter
     ~   properties first appeared when scaling models to 4            model is also competitive with the best large lan-
    on   sufficient size (Kaplan et al., 2020), resulting in a         guage models such as Chinchilla or PALM-540B.
         line of work that focuses on further scaling these
         models (Chowdhery et al., 2022; Rae et al., 2021).            Unlike Chinchilla,         PaLM, or GPT-3, we only
     =   These efforts    are  based  on    the    assumption that     use publicly available data, making our work com-
     =   more parameters will lead to better performance.              patible  with open-sourcing, while   most existing
         However, recent work from Hoffmann et al. 2022                models rely on data which is either not publicly
     >   shows that, for a given compute budget, the best              available or undocumented (e.g.   “Books — 2TB” or
         performances are not achieved by the largest mod-     “Social media                             There exist some
         els, but by smaller models trained on more data.              exceptions, notably     OPT (Zhang  et al., 2022),
     <         The objective   of the scaling     laws    from Hoff-   GPT-NeoX (Black et al., 2022),         BLOOM (Scao
         mann et al.           2022 is to determine    how to best             2022 and GLM (Zeng et al., 2022), but none
         scale the dataset and model sizes for a particular            that are competitive with PALM-62B or Chinchilla.
         training compute budget. However, this objective
         disregards the   inference budget,          which becomes      In the rest of this paper, we present an overview
        critical when serving a language model at scale. of the modifications we made to the transformer
        In this context, given a target level of performance, architecture (Vaswani et al., 2017), as well as our
        the preferred model is not the fastest to train but the training method. We then report the performance of
        fastest at inference, and although it may be cheaper ~~ our models and compare with others LLMs on a set
        to train a large model to reach a certain level of of standard benchmarks. Finally, we expose some
         _                                                             of the biases and toxicity encoded in our models,
                 Equal contribution.  Correspondence:   {htouvron,     .
         thibautlav,gizacard,egrave,glample}@meta.com                       using some of the most recent benchmarks from
            "https: //github.com/facebookresearch/11ama                the responsible AI community.

